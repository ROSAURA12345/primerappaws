from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
import mysql.connector
from datetime import datetime, timedelta
import re

app = Flask(__name__)
app.secret_key = 'clave_secreta_biblioteca_2024'
@app.context_processor
def inject_now():
    return {'now': datetime.now()}
# Configuración de la base de datos
def get_db_connection():
    try:
        conn = mysql.connector.connect(
            host='localhost',
            user='root',
            password='',
            database='biblioteca',
            charset='utf8mb4',
            collation='utf8mb4_unicode_ci'
        )
        return conn
    except mysql.connector.Error as err:
        print(f"❌ Error de conexión: {err}")
        return None

# Crear tablas si no existen
def crear_tablas():
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            
            # Tabla libros
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS libros (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    titulo VARCHAR(255) NOT NULL,
                    autor VARCHAR(255) NOT NULL,
                    isbn VARCHAR(20) UNIQUE,
                    genero VARCHAR(100),
                    anio_publicacion INT,
                    editorial VARCHAR(255),
                    ejemplares INT DEFAULT 1,
                    ejemplares_disponibles INT DEFAULT 1,
                    fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Tabla préstamos
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS prestamos (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    libro_id INT,
                    nombre_prestatario VARCHAR(255) NOT NULL,
                    email_prestatario VARCHAR(255),
                    telefono VARCHAR(20),
                    fecha_prestamo DATE NOT NULL,
                    fecha_devolucion DATE,
                    fecha_devolucion_real DATE,
                    estado ENUM('prestado', 'devuelto', 'atrasado') DEFAULT 'prestado',
                    observaciones TEXT,
                    FOREIGN KEY (libro_id) REFERENCES libros(id) ON DELETE CASCADE
                )
            ''')
            
            conn.commit()
            print("✅ Tablas creadas/verificadas correctamente")
            
        except mysql.connector.Error as err:
            print(f"❌ Error al crear tablas: {err}")
        finally:
            cursor.close()
            conn.close()

# Inicializar aplicación
def inicializar_app():
    print("🚀 Inicializando Sistema de Biblioteca...")
    crear_tablas()

inicializar_app()

# ==================== RUTAS PRINCIPALES ====================

@app.route('/')
def index():
    """Página principal del sistema"""
    conn = get_db_connection()
    if not conn:
        flash('Error de conexión a la base de datos', 'error')
        return render_template('index.html')
    
    try:
        cursor = conn.cursor(dictionary=True)
        
        # Estadísticas generales
        cursor.execute("SELECT COUNT(*) as total FROM libros")
        total_libros = cursor.fetchone()['total']
        
        cursor.execute("SELECT COUNT(*) as total FROM prestamos WHERE estado = 'prestado'")
        prestamos_activos = cursor.fetchone()['total']
        
        cursor.execute("SELECT COUNT(*) as total FROM prestamos WHERE estado = 'atrasado'")
        prestamos_atrasados = cursor.fetchone()['total']
        
        # Libros más populares (con más préstamos)
        cursor.execute('''
            SELECT l.*, COUNT(p.id) as total_prestamos 
            FROM libros l 
            LEFT JOIN prestamos p ON l.id = p.libro_id 
            GROUP BY l.id 
            ORDER BY total_prestamos DESC 
            LIMIT 5
        ''')
        libros_populares = cursor.fetchall()
        
        # Préstamos recientes
        cursor.execute('''
            SELECT p.*, l.titulo, l.autor 
            FROM prestamos p 
            JOIN libros l ON p.libro_id = l.id 
            ORDER BY p.fecha_prestamo DESC 
            LIMIT 5
        ''')
        prestamos_recientes = cursor.fetchall()
        
        # Formatear fechas
        for prestamo in prestamos_recientes:
            if prestamo['fecha_prestamo']:
                prestamo['fecha_prestamo'] = prestamo['fecha_prestamo'].strftime('%d/%m/%Y')
            if prestamo['fecha_devolucion']:
                prestamo['fecha_devolucion'] = prestamo['fecha_devolucion'].strftime('%d/%m/%Y')
        
        cursor.close()
        conn.close()
        
        return render_template('index.html',
                             total_libros=total_libros,
                             prestamos_activos=prestamos_activos,
                             prestamos_atrasados=prestamos_atrasados,
                             libros_populares=libros_populares,
                             prestamos_recientes=prestamos_recientes)
    
    except mysql.connector.Error as err:
        flash(f'Error al cargar datos: {err}', 'error')
        return render_template('index.html')

# ==================== GESTIÓN DE LIBROS ====================

@app.route('/libros')
def listar_libros():
    """Lista todos los libros"""
    busqueda = request.args.get('busqueda', '')
    genero = request.args.get('genero', '')
    
    conn = get_db_connection()
    if not conn:
        flash('Error de conexión a la base de datos', 'error')
        return render_template('libros.html', libros=[])
    
    try:
        cursor = conn.cursor(dictionary=True)
        
        query = "SELECT * FROM libros WHERE 1=1"
        params = []
        
        if busqueda:
            query += " AND (titulo LIKE %s OR autor LIKE %s OR isbn LIKE %s)"
            params.extend([f'%{busqueda}%', f'%{busqueda}%', f'%{busqueda}%'])
        
        if genero:
            query += " AND genero = %s"
            params.append(genero)
        
        query += " ORDER BY titulo"
        cursor.execute(query, params)
        libros = cursor.fetchall()
        
        # Obtener géneros únicos para el filtro
        cursor.execute("SELECT DISTINCT genero FROM libros WHERE genero IS NOT NULL ORDER BY genero")
        generos = [row['genero'] for row in cursor.fetchall()]
        
        cursor.close()
        conn.close()
        
        return render_template('libros.html', libros=libros, generos=generos, busqueda=busqueda, genero_filtro=genero)
    
    except mysql.connector.Error as err:
        flash(f'Error al cargar libros: {err}', 'error')
        return render_template('libros.html', libros=[])

@app.route('/libros/agregar', methods=['GET', 'POST'])
def agregar_libro():
    """Agregar nuevo libro"""
    if request.method == 'POST':
        titulo = request.form.get('titulo', '').strip()
        autor = request.form.get('autor', '').strip()
        isbn = request.form.get('isbn', '').strip()
        genero = request.form.get('genero', '').strip()
        anio_publicacion = request.form.get('anio_publicacion')
        editorial = request.form.get('editorial', '').strip()
        ejemplares = request.form.get('ejemplares', 1)
        
        # Validaciones
        if not titulo or not autor:
            flash('El título y autor son obligatorios', 'error')
            return render_template('agregar_libro.html')
        
        if isbn and len(isbn) > 20:
            flash('El ISBN no puede tener más de 20 caracteres', 'error')
            return render_template('agregar_libro.html')
        
        try:
            ejemplares = int(ejemplares)
            if ejemplares < 1:
                flash('Debe haber al menos 1 ejemplar', 'error')
                return render_template('agregar_libro.html')
        except ValueError:
            flash('Número de ejemplares inválido', 'error')
            return render_template('agregar_libro.html')
        
        conn = get_db_connection()
        if not conn:
            flash('Error de conexión a la base de datos', 'error')
            return render_template('agregar_libro.html')
        
        try:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO libros 
                (titulo, autor, isbn, genero, anio_publicacion, editorial, ejemplares, ejemplares_disponibles) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (titulo, autor, isbn or None, genero or None, anio_publicacion, editorial or None, ejemplares, ejemplares)
            )
            conn.commit()
            cursor.close()
            conn.close()
            flash('✅ Libro agregado correctamente', 'success')
            return redirect(url_for('listar_libros'))
        
        except mysql.connector.IntegrityError:
            flash('❌ Error: El ISBN ya existe en la base de datos', 'error')
        except mysql.connector.Error as err:
            flash(f'❌ Error al agregar libro: {err}', 'error')
        
        return render_template('agregar_libro.html')
    
    return render_template('agregar_libro.html')

@app.route('/libros/editar/<int:id>', methods=['GET', 'POST'])
def editar_libro(id):
    """Editar libro existente"""
    conn = get_db_connection()
    if not conn:
        flash('Error de conexión a la base de datos', 'error')
        return redirect(url_for('listar_libros'))
    
    if request.method == 'GET':
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM libros WHERE id = %s", (id,))
            libro = cursor.fetchone()
            
            if not libro:
                flash('Libro no encontrado', 'error')
                return redirect(url_for('listar_libros'))
            
            cursor.close()
            conn.close()
            return render_template('editar_libro.html', libro=libro)
        
        except mysql.connector.Error as err:
            flash(f'Error al cargar libro: {err}', 'error')
            return redirect(url_for('listar_libros'))
    
    else:  # POST
        titulo = request.form.get('titulo', '').strip()
        autor = request.form.get('autor', '').strip()
        isbn = request.form.get('isbn', '').strip()
        genero = request.form.get('genero', '').strip()
        anio_publicacion = request.form.get('anio_publicacion')
        editorial = request.form.get('editorial', '').strip()
        ejemplares = request.form.get('ejemplares', 1)
        
        # Validaciones
        if not titulo or not autor:
            flash('El título y autor son obligatorios', 'error')
            return redirect(url_for('editar_libro', id=id))
        
        try:
            ejemplares = int(ejemplares)
            if ejemplares < 1:
                flash('Debe haber al menos 1 ejemplar', 'error')
                return redirect(url_for('editar_libro', id=id))
        except ValueError:
            flash('Número de ejemplares inválido', 'error')
            return redirect(url_for('editar_libro', id=id))
        
        try:
            cursor = conn.cursor()
            
            # Calcular nuevos ejemplares disponibles
            cursor.execute("SELECT ejemplares, ejemplares_disponibles FROM libros WHERE id = %s", (id,))
            libro_actual = cursor.fetchone()
            
            diferencia_ejemplares = ejemplares - libro_actual[0]
            nuevos_disponibles = libro_actual[1] + diferencia_ejemplares
            
            if nuevos_disponibles < 0:
                flash('No puede reducir ejemplares por debajo de los prestados', 'error')
                return redirect(url_for('editar_libro', id=id))
            
            cursor.execute(
                """UPDATE libros 
                SET titulo=%s, autor=%s, isbn=%s, genero=%s, anio_publicacion=%s, 
                    editorial=%s, ejemplares=%s, ejemplares_disponibles=%s 
                WHERE id=%s""",
                (titulo, autor, isbn or None, genero or None, anio_publicacion, 
                 editorial or None, ejemplares, nuevos_disponibles, id)
            )
            conn.commit()
            cursor.close()
            conn.close()
            flash('✅ Libro actualizado correctamente', 'success')
        
        except mysql.connector.IntegrityError:
            flash('❌ Error: El ISBN ya existe en la base de datos', 'error')
        except mysql.connector.Error as err:
            flash(f'❌ Error al actualizar libro: {err}', 'error')
        
        return redirect(url_for('listar_libros'))

@app.route('/libros/eliminar/<int:id>')
def eliminar_libro(id):
    """Eliminar libro"""
    conn = get_db_connection()
    if not conn:
        flash('Error de conexión a la base de datos', 'error')
        return redirect(url_for('listar_libros'))
    
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM libros WHERE id = %s", (id,))
        conn.commit()
        cursor.close()
        conn.close()
        flash('✅ Libro eliminado correctamente', 'success')
    except mysql.connector.Error as err:
        flash(f'❌ Error al eliminar libro: {err}', 'error')
    
    return redirect(url_for('listar_libros'))

# ==================== GESTIÓN DE PRÉSTAMOS ====================

@app.route('/prestamos')
def listar_prestamos():
    """Listar todos los préstamos"""
    estado = request.args.get('estado', '')
    
    conn = get_db_connection()
    if not conn:
        flash('Error de conexión a la base de datos', 'error')
        return render_template('prestamos.html', prestamos=[])
    
    try:
        cursor = conn.cursor(dictionary=True)
        
        query = '''
            SELECT p.*, l.titulo, l.autor, l.isbn 
            FROM prestamos p 
            JOIN libros l ON p.libro_id = l.id 
            WHERE 1=1
        '''
        params = []
        
        if estado:
            query += " AND p.estado = %s"
            params.append(estado)
        
        query += " ORDER BY p.fecha_prestamo DESC"
        cursor.execute(query, params)
        prestamos = cursor.fetchall()
        
        # Formatear fechas
        for prestamo in prestamos:
            if prestamo['fecha_prestamo']:
                prestamo['fecha_prestamo'] = prestamo['fecha_prestamo'].strftime('%d/%m/%Y')
            if prestamo['fecha_devolucion']:
                prestamo['fecha_devolucion'] = prestamo['fecha_devolucion'].strftime('%d/%m/%Y')
            if prestamo['fecha_devolucion_real']:
                prestamo['fecha_devolucion_real'] = prestamo['fecha_devolucion_real'].strftime('%d/%m/%Y')
        
        cursor.close()
        conn.close()
        
        return render_template('prestamos.html', prestamos=prestamos, estado_filtro=estado)
    
    except mysql.connector.Error as err:
        flash(f'Error al cargar préstamos: {err}', 'error')
        return render_template('prestamos.html', prestamos=[])

@app.route('/prestamos/nuevo', methods=['GET', 'POST'])
def nuevo_prestamo():
    """Crear nuevo préstamo"""
    if request.method == 'POST':
        libro_id = request.form.get('libro_id')
        nombre_prestatario = request.form.get('nombre_prestatario', '').strip()
        email_prestatario = request.form.get('email_prestatario', '').strip()
        telefono = request.form.get('telefono', '').strip()
        fecha_prestamo = request.form.get('fecha_prestamo')
        fecha_devolucion = request.form.get('fecha_devolucion')
        observaciones = request.form.get('observaciones', '').strip()
        
        # Validaciones
        if not libro_id or not nombre_prestatario or not fecha_prestamo or not fecha_devolucion:
            flash('Todos los campos obligatorios deben ser completados', 'error')
            return redirect(url_for('nuevo_prestamo'))
        
        if fecha_devolucion <= fecha_prestamo:
            flash('La fecha de devolución debe ser posterior a la fecha de préstamo', 'error')
            return redirect(url_for('nuevo_prestamo'))
        
        conn = get_db_connection()
        if not conn:
            flash('Error de conexión a la base de datos', 'error')
            return redirect(url_for('nuevo_prestamo'))
        
        try:
            cursor = conn.cursor()
            
            # Verificar disponibilidad
            cursor.execute("SELECT ejemplares_disponibles FROM libros WHERE id = %s", (libro_id,))
            libro = cursor.fetchone()
            
            if not libro or libro[0] < 1:
                flash('No hay ejemplares disponibles de este libro', 'error')
                return redirect(url_for('nuevo_prestamo'))
            
            # Crear préstamo
            cursor.execute(
                """INSERT INTO prestamos 
                (libro_id, nombre_prestatario, email_prestatario, telefono, fecha_prestamo, fecha_devolucion, observaciones) 
                VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (libro_id, nombre_prestatario, email_prestatario or None, telefono or None, 
                 fecha_prestamo, fecha_devolucion, observaciones or None)
            )
            
            # Actualizar disponibilidad
            cursor.execute(
                "UPDATE libros SET ejemplares_disponibles = ejemplares_disponibles - 1 WHERE id = %s",
                (libro_id,)
            )
            
            conn.commit()
            cursor.close()
            conn.close()
            flash('✅ Préstamo registrado correctamente', 'success')
        
        except mysql.connector.Error as err:
            flash(f'❌ Error al registrar préstamo: {err}', 'error')
        
        return redirect(url_for('listar_prestamos'))
    
    else:  # GET
        conn = get_db_connection()
        if not conn:
            flash('Error de conexión a la base de datos', 'error')
            return render_template('nuevo_prestamo.html', libros=[])
        
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT id, titulo, autor FROM libros WHERE ejemplares_disponibles > 0 ORDER BY titulo")
            libros = cursor.fetchall()
            cursor.close()
            conn.close()
            
            fecha_hoy = datetime.now().strftime('%Y-%m-%d')
            fecha_devolucion = (datetime.now() + timedelta(days=15)).strftime('%Y-%m-%d')
            
            return render_template('nuevo_prestamo.html', libros=libros, fecha_hoy=fecha_hoy, fecha_devolucion=fecha_devolucion)
        
        except mysql.connector.Error as err:
            flash(f'Error al cargar libros: {err}', 'error')
            return render_template('nuevo_prestamo.html', libros=[])

@app.route('/prestamos/devolver/<int:id>')
def devolver_prestamo(id):
    """Registrar devolución de préstamo"""
    conn = get_db_connection()
    if not conn:
        flash('Error de conexión a la base de datos', 'error')
        return redirect(url_for('listar_prestamos'))
    
    try:
        cursor = conn.cursor(dictionary=True)
        
        # Obtener información del préstamo
        cursor.execute("SELECT libro_id, estado FROM prestamos WHERE id = %s", (id,))
        prestamo = cursor.fetchone()
        
        if not prestamo:
            flash('Préstamo no encontrado', 'error')
            return redirect(url_for('listar_prestamos'))
        
        if prestamo['estado'] == 'devuelto':
            flash('Este préstamo ya fue devuelto', 'warning')
            return redirect(url_for('listar_prestamos'))
        
        # Actualizar préstamo
        fecha_devolucion = datetime.now().date()
        cursor.execute(
            "UPDATE prestamos SET estado = 'devuelto', fecha_devolucion_real = %s WHERE id = %s",
            (fecha_devolucion, id)
        )
        
        # Actualizar disponibilidad del libro
        cursor.execute(
            "UPDATE libros SET ejemplares_disponibles = ejemplares_disponibles + 1 WHERE id = %s",
            (prestamo['libro_id'],)
        )
        
        conn.commit()
        cursor.close()
        conn.close()
        flash('✅ Devolución registrada correctamente', 'success')
    
    except mysql.connector.Error as err:
        flash(f'❌ Error al registrar devolución: {err}', 'error')
    
    return redirect(url_for('listar_prestamos'))

@app.route('/prestamos/eliminar/<int:id>')
def eliminar_prestamo(id):
    """Eliminar préstamo (solo si está devuelto)"""
    conn = get_db_connection()
    if not conn:
        flash('Error de conexión a la base de datos', 'error')
        return redirect(url_for('listar_prestamos'))
    
    try:
        cursor = conn.cursor(dictionary=True)
        
        # Verificar estado del préstamo
        cursor.execute("SELECT libro_id, estado FROM prestamos WHERE id = %s", (id,))
        prestamo = cursor.fetchone()
        
        if not prestamo:
            flash('Préstamo no encontrado', 'error')
            return redirect(url_for('listar_prestamos'))
        
        if prestamo['estado'] != 'devuelto':
            flash('Solo se pueden eliminar préstamos que ya fueron devueltos', 'error')
            return redirect(url_for('listar_prestamos'))
        
        # Eliminar préstamo
        cursor.execute("DELETE FROM prestamos WHERE id = %s", (id,))
        conn.commit()
        cursor.close()
        conn.close()
        flash('✅ Préstamo eliminado correctamente', 'success')
    
    except mysql.connector.Error as err:
        flash(f'❌ Error al eliminar préstamo: {err}', 'error')
    
    return redirect(url_for('listar_prestamos'))

# ==================== APIs ====================

@app.route('/api/libros/disponibles')
def api_libros_disponibles():
    """API para obtener libros disponibles (para AJAX)"""
    conn = get_db_connection()
    if not conn:
        return jsonify([])
    
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, titulo, autor FROM libros WHERE ejemplares_disponibles > 0 ORDER BY titulo")
        libros = cursor.fetchall()
        cursor.close()
        conn.close()
        return jsonify(libros)
    except mysql.connector.Error:
        return jsonify([])

if __name__ == '__main__':
    print("🌐 Iniciando Sistema de Biblioteca...")
    print("📚 Gestión completa de libros y préstamos")
    print("🔗 Disponible en: http://localhost:5000")
    app.run(debug=True, host='0.0.0.0', port=5000)