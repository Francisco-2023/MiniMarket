from flask import Flask, render_template, request, redirect, session, url_for, abort
import firebase_admin
from firebase_admin import credentials, firestore
import pyrebase
from firebase_admin import storage
import uuid
import os
import json
from flask import jsonify
from flask import flash
from werkzeug.utils import secure_filename
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'clave_secreta_segura'

# Configuración Firebase Web SDK (copiado desde consola)
firebaseConfig = {
    "apiKey": "AIzaSyBpj6Ui7g3Rk2W5iFsNAs6UERb4miG53N8",
    "authDomain": "minimarket-7fba7.firebaseapp.com",
    "projectId": "minimarket-7fba7",
    "storageBucket": "minimarket-7fba7.appspot.com",
    "messagingSenderId": "397276893672",
    "appId": "1:397276893672:web:287e3d57f22d1426be545d",
    "measurementId": "G-1S5MMTP5GJ",
    "databaseURL": ""  # No se usa Fire Realtime DB, solo Firestore
}

# Inicializar Firebase Auth (Pyrebase)
firebase = pyrebase.initialize_app(firebaseConfig)
auth = firebase.auth()

# Inicializar Firebase Admin SDK (Firestore)
cred = credentials.Certificate("minimarket-7fba7-firebase-adminsdk-fbsvc-ffb97d15f3.json")
firebase_admin.initialize_app(cred, {
    'storageBucket': 'minimarket-7fba7.appspot.com'
})
db = firestore.client()

from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, EmailField, SubmitField
from wtforms.validators import DataRequired, Email, EqualTo, Length
# Flask-WTF Form for Registration
class RegisterForm(FlaskForm):
    nombre = StringField('Nombre', validators=[DataRequired(), Length(min=2, max=50)])
    email = EmailField('Correo Electrónico', validators=[DataRequired(), Email()])
    password = PasswordField('Contraseña', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirmar Contraseña', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Registrarse')

# RUTA RAÍZ
@app.route('/')
def index():
    return redirect(url_for('login'))

# LOGIN
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        if not email or not password:
            flash('Por favor, completa todos los campos.', 'error')
            return render_template('login.html')
        try:
            user = auth.sign_in_with_email_and_password(email, password)
            session['usuario'] = email
            flash('Inicio de sesión exitoso.', 'success')
            return redirect(url_for('dashboard'))
        except Exception as e:
            mensaje = str(e)
            if 'INVALID_PASSWORD' in mensaje:
                flash('La contraseña es incorrecta.', 'error')
            elif 'EMAIL_NOT_FOUND' in mensaje:
                flash('No existe una cuenta con este correo.', 'error')
            else:
                flash('Credenciales inválidas. Intenta nuevamente.', 'error')
    return render_template('login.html')

# REGISTRO
@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        try:
            # Crear usuario en Firebase Auth
            user = auth.create_user_with_email_and_password(form.email.data, form.password.data)
            # Guardar info en Firestore
            db.collection('usuarios').document(form.email.data).set({
                'email': form.email.data,
                'nombre': form.nombre.data,
                'rol': 'usuario'
            })
            flash('Usuario registrado correctamente.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            mensaje = str(e)
            if 'EMAIL_EXISTS' in mensaje:
                flash('El correo ya está registrado.', 'error')
            elif 'WEAK_PASSWORD' in mensaje:
                flash('La contraseña es muy débil. Usa al menos 6 caracteres.', 'error')
            else:
                flash('Ocurrió un error durante el registro. Intenta nuevamente.', 'error')
    return render_template('register.html', form=form)

# CERRAR SESIÓN
@app.route('/logout')
def logout():
    session.clear()
    flash('Sesión cerrada correctamente.', 'success')
    return redirect(url_for('login'))

@app.route('/recuperar_password', methods=['GET', 'POST'])
def recuperar_password():
    mensaje = ''
    if request.method == 'POST':
        email = request.form['email']
        try:
            auth.send_password_reset_email(email)
            mensaje = '📧 Se ha enviado un enlace de recuperación a tu correo.'
        except Exception as e:
            mensaje = '❌ No se pudo enviar el correo. Verifica el email o intenta más tarde.'
    return render_template('recuperar_password.html', mensaje=mensaje)

# DASHBOARD
@app.route('/dashboard')
def dashboard():
    # Obtener productos
    productos_ref = db.collection('productos')
    productos_docs = productos_ref.stream()

    productos = []
    total_productos = 0
    stock_bajo = 0

    for doc in productos_docs:
        p = doc.to_dict()
        p['id'] = doc.id
        productos.append(p)
        total_productos += 1
        if p.get('stock', 0) < 5:
            stock_bajo += 1

    # Ordenar productos por fecha_creacion (si existe) y obtener los últimos 8
    productos_ordenados = sorted(productos, key=lambda p: p.get('fecha_creacion', ''), reverse=True)
    ultimos_productos = productos_ordenados[:8]

    # Obtener ventas
    ventas_ref = db.collection('ventas')
    ventas_docs = ventas_ref.stream()
    total_ventas = sum(v.to_dict().get('monto_total', 0) for v in ventas_docs)

    return render_template('dashboard.html',
                           total_productos=total_productos,
                           stock_bajo=stock_bajo,
                           total_ventas=total_ventas,
                           ultimos_productos=ultimos_productos)


from uuid import uuid4

# LISTAR PRODUCTOS
@app.route('/productos')
def productos():
    if 'usuario' not in session:
        return redirect(url_for('login'))

    per_page = 10
    page = request.args.get('page', 1, type=int)

    productos_ref = db.collection('productos').order_by('nombre')

    # En esta demo no uso start_after, sólo primeros 10 para page=1
    if page == 1:
        docs = productos_ref.limit(per_page).stream()
    else:
        # Necesitas guardar el último documento de la página anterior para usar start_after()
        # Esto requiere manejar estado entre requests o usar otro enfoque
        # Por simplicidad, mostramos todos (mal para muchos datos)
        docs = productos_ref.stream()

    productos = []
    for doc in docs:
        data = doc.to_dict()
        data['id'] = doc.id
        productos.append(data)

    # Aquí igual puedes hacer paginación en Python, pero pierdes eficiencia
    total = len(productos)
    start = (page - 1) * per_page
    end = start + per_page
    productos_page = productos[start:end]

    total_pages = (total + per_page - 1) // per_page

    return render_template('productos.html', productos=productos_page, page=page, datetime=datetime, total_pages=total_pages)

# AGREGAR PRODUCTO
import os
from werkzeug.utils import secure_filename

UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

@app.route('/productos/nuevo', methods=['POST'])
def nuevo_producto():
    if 'usuario' not in session:
        return redirect(url_for('login'))

    nombre = request.form.get('nombre', '').strip()
    precio_proveedor = request.form.get('precio_proveedor', '0').strip()
    precio_salida = request.form.get('precio_salida', '0').strip()
    stock = request.form.get('stock', '0').strip()
    categoria = request.form.get('categoria', '').strip()
    descripcion = request.form.get('descripcion', '').strip()
    codigo = request.form.get('codigo', '').strip()
    imagen = request.files.get('imagen')

    try:
        precio_proveedor = float(precio_proveedor)
        precio_salida = float(precio_salida)
        stock = int(stock)
    except ValueError:
        return "Error: Datos numéricos inválidos.", 400

    if imagen and imagen.filename != '':
        filename = secure_filename(imagen.filename)
        ruta_guardado = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        imagen.save(ruta_guardado)
        url_imagen = f'/static/uploads/{filename}'
    else:
        url_imagen = ''

    db.collection('productos').add({
    'codigo': codigo,
    'nombre': nombre,
    'precio_proveedor': precio_proveedor,
    'precio_salida': precio_salida,
    'stock': stock,
    'categoria': categoria,
    'descripcion': descripcion,
    'imagen': url_imagen,
    'marca': request.form.get('marca', '').strip(),
    'unidad_medida': request.form.get('unidad_medida', '').strip()
})

    return redirect(url_for('productos'))

@app.route('/productos/editar/<producto_id>', methods=['POST'])
def editar_producto(producto_id):
    if 'usuario' not in session:
        return redirect(url_for('login'))

    # Campos recibidos del formulario
    nombre = request.form.get('nombre', '').strip()
    precio_proveedor = request.form.get('precio_proveedor', '0').strip()
    precio_salida = request.form.get('precio_salida', '0').strip()
    stock = request.form.get('stock', '0').strip()
    categoria = request.form.get('categoria', '').strip()
    descripcion = request.form.get('descripcion', '').strip()
    codigo = request.form.get('codigo', '').strip()
    marca = request.form.get('marca', '').strip()
    unidad_medida = request.form.get('unidad_medida', '').strip()
    imagen = request.files.get('imagen')

    # Validación numérica
    try:
        precio_proveedor = float(precio_proveedor)
        precio_salida = float(precio_salida)
        stock = int(stock)
    except ValueError:
        return "Error: Datos numéricos inválidos.", 400

    # Datos a actualizar
    datos_actualizados = {
        'nombre': nombre,
        'precio_proveedor': precio_proveedor,
        'precio_salida': precio_salida,
        'stock': stock,
        'categoria': categoria,
        'descripcion': descripcion,
        'codigo': codigo,
        'marca': marca,
        'unidad_medida': unidad_medida
    }

    # Obtener documento actual para conservar imagen si no se sube nueva
    doc_ref = db.collection('productos').document(producto_id)
    producto_actual = doc_ref.get().to_dict()

    if imagen and imagen.filename != '':
        # Subida de nueva imagen
        nombre_archivo = secure_filename(imagen.filename)
        ruta_local = f"/tmp/{nombre_archivo}"
        imagen.save(ruta_local)

        bucket = storage.bucket()
        blob = bucket.blob(f'productos/{uuid.uuid4()}-{nombre_archivo}')
        blob.upload_from_filename(ruta_local)
        blob.make_public()
        url_imagen = blob.public_url
        datos_actualizados['imagen'] = url_imagen
        os.remove(ruta_local)
    else:
        # Mantener imagen anterior
        if 'imagen' in producto_actual:
            datos_actualizados['imagen'] = producto_actual['imagen']

    # Actualizar producto
    doc_ref.update(datos_actualizados)

    return redirect(url_for('productos'))


# ELIMINAR PRODUCTO
@app.route('/productos/eliminar/<id>')
def eliminar_producto(id):
    if 'usuario' not in session:
        return redirect(url_for('login'))
    db.collection('productos').document(id).delete()
    return redirect(url_for('productos'))


@app.route('/vender', methods=['POST'])
def vender():
    if 'usuario' not in session:
        return redirect(url_for('login'))

    items = request.form.getlist('productos[]')
    cantidades = request.form.getlist('cantidades[]')
    nombres = request.form.getlist('nombres[]')
    precios = request.form.getlist('precios[]')
    subtotales = request.form.getlist('subtotales[]')

    if not items or not cantidades or len(items) != len(cantidades):
        flash('Datos de venta incompletos.', 'danger')
        return redirect(url_for('facturacion'))

    try:
        # Validar stock
        for i, prod_id in enumerate(items):
            doc = db.collection('productos').document(prod_id).get()
            if not doc.exists:
                flash(f'Producto con ID {prod_id} no existe.', 'danger')
                return redirect(url_for('facturacion'))

            producto = doc.to_dict()
            cantidad = int(cantidades[i])
            if cantidad <= 0:
                flash(f'Cantidad inválida para {producto["nombre"]}.', 'danger')
                return redirect(url_for('facturacion'))

            if producto.get('stock', 0) < cantidad:
                flash(f'Stock insuficiente para {producto["nombre"]}.', 'danger')
                return redirect(url_for('facturacion'))

        # Descontar stock con batch
        batch = db.batch()
        for i, prod_id in enumerate(items):
            cantidad = int(cantidades[i])
            prod_ref = db.collection('productos').document(prod_id)
            producto = prod_ref.get().to_dict()
            nuevo_stock = producto.get('stock', 0) - cantidad
            batch.update(prod_ref, {'stock': nuevo_stock})
        batch.commit()

        # Obtener datos para la factura
        total = float(request.form.get('total', 0))
        cliente = request.form.get('cliente', 'Cliente General')

        detalles = []
        for i in range(len(items)):
            detalles.append({
                'producto_id': items[i],
                'nombre': nombres[i],
                'cantidad': int(cantidades[i]),
                'precio_unitario': float(precios[i]),
                'subtotal': float(subtotales[i])
            })

        factura_data = {
            'fecha': datetime.utcnow(),
            'cliente': cliente,
            'total': total,
            'detalles': detalles
        }

        factura_ref = db.collection('facturas').add(factura_data)

        # Movimiento financiero
        movimiento = {
            'fecha': datetime.utcnow(),
            'tipo': 'entrada',
            'concepto': f'Venta factura {factura_ref[1].id}',
            'monto': total,
            'referencia': factura_ref[1].id,
        }
        db.collection('finanzas').add(movimiento)

        flash('Venta realizada con éxito.', 'success')
        return redirect(url_for('facturacion'))

    except Exception as e:
        flash(f'Ocurrió un error: {str(e)}', 'danger')
        return redirect(url_for('facturacion'))


@app.route('/facturacion')
def facturacion():
    productos_ref = db.collection('productos').stream()
    productos = []
    for doc in productos_ref:
        p = doc.to_dict()
        p['id'] = doc.id
        # Usamos precio_salida como el precio de venta
        p['precio'] = float(p.get('precio_salida', 0))
        productos.append(p)

    return render_template('facturacion.html', productos_json=json.dumps(productos))

from datetime import datetime

from datetime import datetime
import pytz

@app.route('/facturas')
def ver_facturas():
    facturas_ref = db.collection('facturas').stream()
    facturas = []
    for doc in facturas_ref:
        data = doc.to_dict()
        fecha = data.get('fecha')

        if fecha:
            # Firestore Timestamp a datetime local
            try:
                # Si es Firestore Timestamp
                fecha = fecha.astimezone(pytz.timezone('America/Guayaquil'))  # Ajusta según tu zona horaria
            except AttributeError:
                # Si es string, intentar parsear
                try:
                    fecha = datetime.strptime(fecha, '%B %d, %Y at %I:%M:%S %p UTC%z')
                    fecha = fecha.astimezone(pytz.timezone('America/Guayaquil'))
                except Exception:
                    fecha = None
        else:
            fecha = None

        detalles = data.get('detalles', [])
        # Asegurar que precios y subtotales estén como float para Jinja
        for item in detalles:
            item['precio_salida'] = float(item.get('precio_salida', 0))
            item['subtotal'] = float(item.get('subtotal', 0))
            item['cantidad'] = int(item.get('cantidad', 0))
            item['nombre'] = item.get('nombre', 'Producto sin nombre')

        facturas.append({
            'id': doc.id,
            'cliente': data.get('cliente', 'N/A'),
            'fecha': fecha,
            'total': float(data.get('total', 0)),
            'detalles': detalles
        })

    # Ordenar facturas por fecha descendente (más recientes primero)
    facturas.sort(key=lambda f: f['fecha'] or datetime.min, reverse=True)

    return render_template('ver_facturas.html', facturas=facturas)


@app.route('/resumen-financiero')
def resumen_financiero():
    # Ingresos por facturas
    facturas = db.collection('facturas').stream()
    total_facturas = sum(f.to_dict().get('total', 0) for f in facturas)

    # Ingresos por ventas (desde finanzas)
    movimientos_docs = db.collection('finanzas').where('tipo', '==', 'entrada').stream()
    total_ventas = sum(m.to_dict().get('monto', 0) for m in movimientos_docs)

    ingresos = total_facturas + total_ventas

    # Egresos (si los manejas en otra colección o también en 'finanzas')
    egresos_docs = db.collection('finanzas').where('tipo', '==', 'salida').stream()
    egresos = sum(e.to_dict().get('monto', 0) for e in egresos_docs)

    balance = ingresos - egresos

    ingresos_mes = []
    egresos_mes = []
    meses = []

    return render_template('resumen.html',
                           ingresos=ingresos,
                           egresos=egresos,
                           ventas=total_ventas,   # <-- Aquí lo agregas
                           balance=balance,
                           ingresos_mes=ingresos_mes,
                           egresos_mes=egresos_mes,
                           meses=meses)


from collections import defaultdict

@app.route('/reporte', methods=['GET', 'POST'])
def reporte_financiero():
    fecha_inicio = request.form.get('fecha_inicio')
    fecha_fin = request.form.get('fecha_fin')

    movimientos_ref = db.collection('finanzas')
    ventas_ref = db.collection('ventas')

    if fecha_inicio and fecha_fin:
        try:
            start = datetime.strptime(fecha_inicio, '%Y-%m-%d')
            end = datetime.strptime(fecha_fin, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
            movimientos_ref = movimientos_ref.where('fecha', '>=', start).where('fecha', '<=', end)
            ventas_ref = ventas_ref.where('fecha', '>=', start).where('fecha', '<=', end)
        except Exception as e:
            print("Error con las fechas:", e)
            start = end = None
    else:
        start = end = None

    movimientos_docs = movimientos_ref.order_by('fecha').stream()
    ventas_docs = ventas_ref.stream()

    ingresos = egresos = total_ventas = 0
    movimientos = []
    resumen_mensual = defaultdict(lambda: {'ingresos': 0, 'egresos': 0})

    for doc in movimientos_docs:
        m = doc.to_dict()
        if not m.get('fecha'):
            continue
        monto = float(m.get('monto') or 0)
        m['monto'] = monto
        movimientos.append(m)
        clave_mes = m['fecha'].strftime('%b %Y')
        if m.get('tipo') == 'entrada':
            ingresos += monto
            resumen_mensual[clave_mes]['ingresos'] += monto
        else:
            egresos += monto
            resumen_mensual[clave_mes]['egresos'] += monto

    for v in ventas_docs:
        venta = v.to_dict()
        if start and end:
            if 'fecha' not in venta or not (start <= venta['fecha'] <= end):
                continue
        total_ventas += float(venta.get('total', 0))

    meses = sorted(resumen_mensual.keys())
    ingresos_mes = [resumen_mensual[m]['ingresos'] for m in meses]
    egresos_mes = [resumen_mensual[m]['egresos'] for m in meses]

    balance = ingresos - egresos

    return render_template(
        'resumen_filtros.html',
        movimientos=movimientos or [],
        ingresos=ingresos or 0,
        egresos=egresos or 0,
        balance=balance or 0,
        ventas=total_ventas or 0,
        fecha_inicio=fecha_inicio or '',
        fecha_fin=fecha_fin or '',
        ingresos_mes=ingresos_mes or [],
        egresos_mes=egresos_mes or [],
        meses=meses or []
    )


@app.route('/ventas', methods=['GET', 'POST'])
def ventas():
    if 'usuario' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        productos_ids = request.form.getlist('producto_id[]')
        cantidades_str = request.form.getlist('cantidad[]')

        if not productos_ids or not cantidades_str:
            flash('Debes ingresar productos y cantidades.', 'danger')
            return redirect(url_for('ventas'))

        ventas_detalle = []
        try:
            for i, prod_id in enumerate(productos_ids):
                cantidad = int(cantidades_str[i])
                if cantidad <= 0:
                    flash('Las cantidades deben ser mayores a cero.', 'danger')
                    return redirect(url_for('ventas'))

                prod_doc = db.collection('productos').document(prod_id).get()
                if not prod_doc.exists:
                    flash(f'Producto con ID {prod_id} no existe.', 'danger')
                    return redirect(url_for('ventas'))

                producto = prod_doc.to_dict()
                stock_actual = producto.get('stock', 0)
                if stock_actual < cantidad:
                    flash(f'Stock insuficiente para {producto["nombre"]}. Stock actual: {stock_actual}', 'danger')
                    return redirect(url_for('ventas'))

                ventas_detalle.append({
                    'producto_id': prod_id,
                    'nombre': producto['nombre'],
                    'cantidad': cantidad,
                    'precio_unitario': producto.get('precio_salida', 0),
                    'subtotal': producto.get('precio_salida', 0) * cantidad
                })

            batch = db.batch()
            total_venta = 0
            for item in ventas_detalle:
                prod_ref = db.collection('productos').document(item['producto_id'])
                producto_actual = prod_ref.get().to_dict()
                nuevo_stock = producto_actual.get('stock', 0) - item['cantidad']
                batch.update(prod_ref, {'stock': nuevo_stock})
                total_venta += item['subtotal']
            batch.commit()

            venta_data = {
                'fecha': datetime.utcnow(),
                'usuario': session['usuario'],
                'total': total_venta,
                'detalle': ventas_detalle
            }
            venta_ref = db.collection('ventas').add(venta_data)

            movimiento = {
                'fecha': datetime.utcnow(),
                'tipo': 'entrada',
                'concepto': f'Venta {venta_ref[1].id}',
                'monto': total_venta,
                'referencia': venta_ref[1].id
            }
            db.collection('finanzas').add(movimiento)

            flash('Venta registrada con éxito.', 'success')
            return redirect(url_for('ventas'))

        except Exception as e:
            flash(f'Error al registrar la venta: {str(e)}', 'danger')
            return redirect(url_for('ventas'))

    # GET
    productos_docs = db.collection('productos').stream()
    productos = []
    for doc in productos_docs:
        p = doc.to_dict()
        p['id'] = doc.id
        productos.append(p)

    return render_template('ventas.html', productos=productos)

import logging
# Configure logging
logging.basicConfig(level=logging.DEBUG)

@app.route("/roles-pago")
def roles_pago():
    roles_ref = db.collection("roles_pagos")
    docs = roles_ref.stream()

    roles = []
    for doc in docs:
        data = doc.to_dict()
        if data:  # Ensure data exists
            data["id"] = doc.id  # Explicitly add id
            roles.append(data)
        else:
            logging.warning(f"Empty document found with ID: {doc.id}")

    logging.debug(f"Roles data: {roles}")  # Debug output
    return render_template("roles_pago.html", roles=roles)

@app.route("/ver_rol/<string:rol_id>")
def view_rol_detail(rol_id):
    roles_ref = db.collection("roles_pagos")
    doc = roles_ref.document(rol_id).get()

    if doc.exists:
        rol = doc.to_dict()
        rol["id"] = doc.id
        return render_template("roles_pago_detalle.html", rol=rol)
    else:
        abort(404, description="Rol de pago no encontrado")

@app.route("/roles-pago/crear", methods=["POST"])
def crear_rol_pago():
    data = dict(request.form)
    try:
        sueldo = float(data.get("sueldo", 0))
        bono = float(data.get("bono", 0))
        descuento = float(data.get("descuento", 0))
        total = sueldo + bono - descuento

        nuevo_rol = {
            "empleado": data.get("empleado"),
            "cargo": data.get("cargo"),
            "sueldo": sueldo,
            "bono": bono,
            "descuento": descuento,
            "fecha_pago": data.get("fecha_pago"),
            "total": total
        }

        db.collection("roles_pagos").add(nuevo_rol)
        return redirect(url_for("roles_pago"))
    except Exception as e:
        return f"Error al crear rol de pago: {e}"


@app.route("/roles-pago/editar/<rol_id>", methods=["POST"])
def editar_rol_pago(rol_id):
    data = dict(request.form)
    try:
        sueldo = float(data.get("sueldo", 0))
        bono = float(data.get("bono", 0))
        descuento = float(data.get("descuento", 0))
        total = sueldo + bono - descuento

        rol_actualizado = {
            "empleado": data.get("empleado"),
            "cargo": data.get("cargo"),
            "sueldo": sueldo,
            "bono": bono,
            "descuento": descuento,
            "fecha_pago": data.get("fecha_pago"),
            "total": total
        }

        db.collection("roles_pagos").document(rol_id).update(rol_actualizado)
        return redirect(url_for("roles_pago"))
    except Exception as e:
        return f"Error al editar rol de pago: {e}"


@app.route("/roles-pago/eliminar/<rol_id>", methods=["POST"])
def eliminar_rol_pago(rol_id):
    try:
        db.collection("roles_pagos").document(rol_id).delete()
        return redirect(url_for("roles_pago"))
    except Exception as e:
        return f"Error al eliminar rol de pago: {e}"

@app.route('/compras', methods=['GET', 'POST'])
def compras():
    if 'usuario' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        productos_ids = request.form.getlist('producto_id[]')
        cantidades_str = request.form.getlist('cantidad[]')
        precios_str = request.form.getlist('precio_unitario[]')

        if not productos_ids or not cantidades_str:
            flash('Debes ingresar productos, cantidades y precios.', 'danger')
            return redirect(url_for('compras'))

        compras_detalle = []
        try:
            for i, prod_id in enumerate(productos_ids):
                cantidad = int(cantidades_str[i])
                precio = float(precios_str[i])
                if cantidad <= 0 or precio <= 0:
                    flash('Cantidad y precio deben ser mayores a cero.', 'danger')
                    return redirect(url_for('compras'))

                prod_doc = db.collection('productos').document(prod_id).get()
                if not prod_doc.exists:
                    flash(f'Producto con ID {prod_id} no existe.', 'danger')
                    return redirect(url_for('compras'))

                producto = prod_doc.to_dict()
                stock_actual = producto.get('stock', 0)

                compras_detalle.append({
                    'producto_id': prod_id,
                    'nombre': producto['nombre'],
                    'cantidad': cantidad,
                    'precio_unitario': precio,
                    'subtotal': precio * cantidad
                })

            batch = db.batch()
            total_compra = 0
            for item in compras_detalle:
                prod_ref = db.collection('productos').document(item['producto_id'])
                producto_actual = prod_ref.get().to_dict()
                nuevo_stock = producto_actual.get('stock', 0) + item['cantidad']
                batch.update(prod_ref, {
                    'stock': nuevo_stock,
                    'precio_entrada': item['precio_unitario']
                })
                total_compra += item['subtotal']
            batch.commit()

            compra_data = {
                'fecha': datetime.utcnow(),
                'usuario': session['usuario'],
                'total': total_compra,
                'detalle': compras_detalle
            }
            compra_ref = db.collection('compras').add(compra_data)

            movimiento = {
                'fecha': datetime.utcnow(),
                'tipo': 'salida',
                'concepto': f'Compra {compra_ref[1].id}',
                'monto': total_compra,
                'referencia': compra_ref[1].id
            }
            db.collection('finanzas').add(movimiento)

            flash('Compra registrada con éxito.', 'success')
            return redirect(url_for('compras'))

        except Exception as e:
            flash(f'Error al registrar la compra: {str(e)}', 'danger')
            return redirect(url_for('compras'))

    # GET
    productos_docs = db.collection('productos').stream()
    productos = []
    for doc in productos_docs:
        p = doc.to_dict()
        p['id'] = doc.id
        productos.append(p)

    return render_template('compras.html', productos=productos)

@app.route('/historial-compras')
def historial_compras():
    if 'usuario' not in session:
        return redirect(url_for('login'))

    compras_ref = db.collection('compras').order_by('fecha', direction=firestore.Query.DESCENDING).limit(50)
    compras_docs = compras_ref.stream()

    compras = []
    for doc in compras_docs:
        data = doc.to_dict()
        data['id'] = doc.id
        # Formatear fecha para mostrar si quieres
        if 'fecha' in data:
            data['fecha_formateada'] = data['fecha'].strftime('%Y-%m-%d %H:%M:%S')
        compras.append(data)

    return render_template('historial_compras.html', compras=compras)

@app.route('/ventas/historial')
def historial_ventas():
    ventas_docs = db.collection('ventas').stream()
    ventas = []

    for doc in ventas_docs:
        v = doc.to_dict()
        v['id'] = doc.id
        v['fecha'] = v['fecha'].astimezone().strftime('%Y-%m-%d')
        ventas.append(v)

    # Agrupación
    ventas_por_dia = {}
    ventas_por_mes = {}
    ventas_por_anio = {}

    for v in ventas:
        fecha = datetime.strptime(v['fecha'], '%Y-%m-%d')
        dia = fecha.strftime('%Y-%m-%d')
        mes = fecha.strftime('%Y-%m')
        anio = fecha.strftime('%Y')

        ventas_por_dia.setdefault(dia, []).append(v)
        ventas_por_mes.setdefault(mes, []).append(v)
        ventas_por_anio.setdefault(anio, []).append(v)

    def calcular_totales(ventas_dict):
        resumen = {}
        for periodo, lista in ventas_dict.items():
            total = sum(v['total'] for v in lista)
            cantidad = sum(sum(p['cantidad'] for p in v['detalle']) for v in lista)
            resumen[periodo] = {
                'total': total,
                'cantidad': cantidad,
                'ventas': lista
            }
        return resumen

    resumen_dia = calcular_totales(ventas_por_dia)
    resumen_mes = calcular_totales(ventas_por_mes)
    resumen_anio = calcular_totales(ventas_por_anio)

    return render_template('historial_ventas.html',
                           resumen_dia=resumen_dia,
                           resumen_mes=resumen_mes,
                           resumen_anio=resumen_anio)


# INICIAR APP
if __name__ == '__main__':
    app.run(debug=True)
