import os
import requests
import io
import csv
import re # Para limpieza de etiquetas y normalización avanzada
from flask import Flask, request, jsonify, render_template, redirect, url_for, flash, make_response
from models import db, User, Area, Vehicle, TallerEntrada, Nota, Checklist, MEXICO_TZ
from dotenv import load_dotenv
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from datetime import datetime
import pytz 
from flask_migrate import Migrate
from sqlalchemy import func, or_
from flask_socketio import SocketIO

# Cargar variables .env
load_dotenv()

app = Flask(__name__)

# --- Configuración General de la App ---
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'una-clave-secreta-muy-dificil')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    'DATABASE_URL', 
    'sqlite:///' + os.path.join(app.root_path, 'taller.db')
).replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
migrate = Migrate(app, db) 

# --- Configuración de SocketIO ---
socketio = SocketIO(app)

# --- Configuración de Flask-Login ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = "Necesitas iniciar sesión para ver esta página."
login_manager.login_message_category = "danger"

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# --- Utilidades de Normalización para el MATCH ---
def normalize_unit_name(name):
    """Quita guiones, espacios y convierte a mayúsculas para un match infalible."""
    if not name: return ""
    return re.sub(r'[^a-zA-Z0-9]', '', str(name)).upper()

def get_unit_root(name):
    """
    Extrae la raíz de una unidad (ej. PR1568-D -> PR1568).
    Busca la secuencia de letras seguidas de números e ignora sufijos posteriores.
    """
    norm = normalize_unit_name(name)
    # Busca la parte alfanumérica base (Letras + Números)
    match = re.search(r'^([A-Z]+[0-9]+)', norm)
    if match:
        return match.group(1)
    return norm

# --- Rutas de Autenticación ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('index'))
        else:
            flash('Usuario o contraseña incorrectos')

    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# --- Rutas de Vistas ---

@app.route('/')
@login_required
def index():
    # Verificación de Acceso al Dashboard
    if not current_user.perm_taller_acceso and current_user.role != 'Superusuario':
        flash('No tienes permiso para ver este dashboard.', 'danger')
        return redirect(url_for('logout'))
    
    # Pasamos el usuario completo para la lógica de visualización
    return render_template('index.html', user=current_user, user_role=current_user.role)

@app.route('/reportes')
@login_required
def reportes():
    if current_user.role not in ['Gerente', 'Superusuario']:
        return redirect(url_for('index'))
    return render_template('reportes.html', user_role=current_user.role)

@app.route('/admin')
@login_required
def admin_panel():
    if current_user.role != 'Superusuario':
        flash('No tienes permiso para acceder a esta página.', 'danger')
        return redirect(url_for('index'))
    return render_template('admin.html', user_role=current_user.role)

@app.route('/stats')
@login_required
def stats_redirect():
    return redirect(url_for('stats', status='activas'))

@app.route('/stats/<status>')
@login_required
def stats(status):
    if status not in ['activas', 'archivadas']:
        return redirect(url_for('stats_redirect'))
    return render_template('stats.html', user_role=current_user.role, status=status)

@app.route('/checklist')
@login_required
def checklist():
    # Verificación Granular de Acceso al Checklist
    if not current_user.perm_checklist_acceso and current_user.role != 'Superusuario':
        return redirect(url_for('index'))
    return render_template('checklist.html', user=current_user, user_role=current_user.role)


# =======================================================
# ---               Rutas de la API (Backend)         ---
# =======================================================

@app.route('/api/entradas', methods=['GET'])
@login_required
def get_entradas_pendientes():
    try:
        filtro_estado = request.args.get('filter', 'todas') 
        search_query = request.args.get('search', '') 
        
        # --- Lógica de Visibilidad Multiarea (MODIFICADA) ---
        if current_user.role in ['Gerente', 'Superusuario'] or current_user.area_id is None:
            query = TallerEntrada.query.filter(
                TallerEntrada.status.in_(['pendiente', 'en_revision'])
            )
        else:
            # Usuarios limitados a una sola área específica
            query = TallerEntrada.query.filter_by(area_id=current_user.area_id)
            
            # Si el usuario es Técnico pero NO Autorizador, solo ve pendientes
            if current_user.perm_taller_tecnico and not current_user.perm_taller_autorizar:
                 query = query.filter_by(status='pendiente')
            else: 
                 query = query.filter(TallerEntrada.status.in_(['pendiente', 'en_revision']))
        
        if search_query:
            query = query.filter(
                or_(
                    TallerEntrada.numero_economico.ilike(f"%{search_query}%"),
                    TallerEntrada.razones.ilike(f"%{search_query}%"),
                    TallerEntrada.otros_motivos.ilike(f"%{search_query}%")
                )
            )

        entradas = query.order_by(TallerEntrada.fecha_entrada.asc()).all()
        
        entradas_filtradas = []
        counts = {"todas": 0, "en_tiempo": 0, "cerca_de_vencer": 0, "fuera_de_tiempo": 0, "en_revision": 0}
        
        for entrada in entradas:
            fecha_entrada_local = entrada.fecha_entrada.replace(tzinfo=pytz.utc).astimezone(MEXICO_TZ)
            dias_en_base = (datetime.now(MEXICO_TZ).date() - fecha_entrada_local.date()).days
            if dias_en_base <= 0: dias_en_base = 1
            
            dias_restantes = entrada.dias_estimados - dias_en_base
            
            if not search_query:
                counts["todas"] += 1
                if entrada.status == 'en_revision':
                    counts["en_revision"] += 1
                
                if dias_restantes < 0:
                    counts["fuera_de_tiempo"] += 1
                elif dias_restantes <= 2:
                    counts["cerca_de_vencer"] += 1
                else:
                    counts["en_tiempo"] += 1

            match = False
            if filtro_estado == 'todas': match = True
            elif filtro_estado == 'fuera_de_tiempo' and dias_restantes < 0: match = True
            elif filtro_estado == 'cerca_de_vencer' and (dias_restantes >= 0 and dias_restantes <= 2): match = True
            elif filtro_estado == 'en_tiempo' and dias_restantes > 2: match = True
            elif filtro_estado == 'en_revision' and entrada.status == 'en_revision': match = True
            
            if match:
                entradas_filtradas.append(entrada.to_dict())

        return jsonify({
            'counts': counts,
            'entradas': entradas_filtradas
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/reportes', methods=['GET'])
@login_required
def get_reportes_archivados():
    if current_user.role not in ['Gerente', 'Superusuario']:
        return jsonify({'error': 'No autorizado'}), 403
    try:
        query = TallerEntrada.query.filter_by(status='archivado')
        entradas = query.order_by(TallerEntrada.fecha_entrada.desc()).all()
        return jsonify([e.to_dict() for e in entradas])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/statistics/summary/<status>')
@login_required
def get_stats_summary(status):
    try:
        if status == 'activas':
            status_filter = TallerEntrada.status.in_(['pendiente', 'en_revision'])
        elif status == 'archivadas':
            status_filter = (TallerEntrada.status == 'archivado')
        else:
            return jsonify({'error': 'Filtro no válido'}), 400
            
        rangos = {
            '1-3 Días': (TallerEntrada.dias_estimados >= 1) & (TallerEntrada.dias_estimados <= 3),
            '4-8 Días': (TallerEntrada.dias_estimados >= 4) & (TallerEntrada.dias_estimados <= 8),
            '9+ Días': TallerEntrada.dias_estimados > 8
        }
        
        query_parts = [TallerEntrada.razones]
        
        for rango_nombre, rango_filtro in rangos.items():
            query_parts.append(
                func.sum(
                    db.case((rango_filtro, 1), else_=0)
                ).label(rango_nombre)
            )
            
        query_parts.append(func.count(TallerEntrada.id).label('total'))
        
        stats_query = db.session.query(*query_parts).filter(status_filter).group_by(TallerEntrada.razones).all()

        results = []
        for row in stats_query:
            row_data = row._asdict()
            row_data['motivo'] = row_data.pop('razones', 'Sin Motivo') or 'Sin Motivo'
            results.append(row_data)

        return jsonify(results)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# --- API: Estadísticas por Operación ---
@app.route('/api/statistics/operations/<status>')
@login_required
def get_stats_operations(status):
    """
    Obtiene las unidades agrupadas por operación.
    Aplica Match Flexible y Match por Raíz para asegurar que remolques (-A, -B, -D) 
    se clasifiquen correctamente usando el catálogo unificado de BDD.
    """
    try:
        status_filter = TallerEntrada.status.in_(['pendiente', 'en_revision']) if status == 'activas' else (TallerEntrada.status == 'archivado')
        
        # 1. Obtener entradas de taller actuales
        entradas = TallerEntrada.query.filter(status_filter).all()
        # 2. Obtener catálogo de vehículos (tractos y remolques) normalizado desde BDD
        vehiculos = Vehicle.query.all()
        mapa_vehiculos = {normalize_unit_name(v.name): v.operation for v in vehiculos}

        grouped = {}
        for ent in entradas:
            eco_original = ent.numero_economico
            eco_norm = normalize_unit_name(eco_original)
            
            # Intento 1: Match Exacto
            op_name = mapa_vehiculos.get(eco_norm)
            
            # Intento 2: Match por Raíz (para sufijos como -A, -B, -D)
            if not op_name:
                raiz = get_unit_root(eco_original)
                op_name = mapa_vehiculos.get(raiz)
            
            final_op = op_name or "Sin Clasificar (No en Samsara)"
            
            if final_op not in grouped:
                grouped[final_op] = []
            grouped[final_op].append(eco_original)

        # 3. Formatear para el frontend con lista de unidades para permitir el click
        results = []
        for op_name, unit_list in grouped.items():
            results.append({
                "operacion": op_name,
                "total": len(unit_list),
                "unidades": sorted(list(set(unit_list))) 
            })
            
        return jsonify(results)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# --- API: Estadísticas por Tipo de Vehículo ---
@app.route('/api/statistics/vehicletypes/<status>')
@login_required
def get_stats_vehicle_types(status):
    """
    Agrupa las entradas de taller por tipo de vehículo (tipo_vehiculo)
    y devuelve la lista de unidades por cada tipo.
    Formato de respuesta: [{ "tipo": "Tractocamión", "total": 5, "unidades": [...] }]
    """
    try:
        if status == 'activas':
            status_filter = TallerEntrada.status.in_(['pendiente', 'en_revision'])
        elif status == 'archivadas':
            status_filter = (TallerEntrada.status == 'archivado')
        else:
            return jsonify({'error': 'Filtro no válido'}), 400

        entradas = TallerEntrada.query.filter(status_filter).all()

        grouped = {}
        for ent in entradas:
            tipo = ent.tipo_vehiculo.strip() if ent.tipo_vehiculo else 'Sin Tipo'
            if tipo not in grouped:
                grouped[tipo] = []
            grouped[tipo].append(ent.numero_economico)

        results = []
        for tipo, unidades in grouped.items():
            results.append({
                'tipo': tipo,
                'total': len(unidades),
                'unidades': sorted(list(set(unidades)))
            })

        # Ordenar de mayor a menor
        results.sort(key=lambda x: x['total'], reverse=True)

        return jsonify(results)

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/statistics/download_csv/<status>')
@login_required
def download_stats_csv(status):
    try:
        if status == 'activas':
            status_filter = TallerEntrada.status.in_(['pendiente', 'en_revision'])
        elif status == 'archivadas':
            status_filter = (TallerEntrada.status == 'archivado')
        else:
            return "Filtro no válido", 400
            
        rangos = {
            '1-3 Días': (TallerEntrada.dias_estimados >= 1) & (TallerEntrada.dias_estimados <= 3),
            '4-8 Días': (TallerEntrada.dias_estimados >= 4) & (TallerEntrada.dias_estimados <= 8),
            '9+ Días': TallerEntrada.dias_estimados > 8
        }
        
        query_parts = [TallerEntrada.razones]
        for rango_nombre, rango_filtro in rangos.items():
            query_parts.append(func.sum(db.case((rango_filtro, 1), else_=0)).label(rango_nombre))
        query_parts.append(func.count(TallerEntrada.id).label('total'))
        
        stats_query = db.session.query(*query_parts).filter(status_filter).group_by(TallerEntrada.razones).all()
        
        si = io.StringIO()
        writer = csv.writer(si)
        
        headers = ['Motivo de Entrada', '1-3 Días', '4-8 Días', '9+ Días', 'Total']
        writer.writerow(headers)
        
        for row in stats_query:
            row_dict = row._asdict()
            writer.writerow([
                row_dict.get('razones', 'Sin Motivo') or 'Sin Motivo',
                row_dict.get('1-3 Días'),
                row_dict.get('4-8 Días'),
                row_dict.get('9+ Días'),
                row_dict.get('total')
            ])

        output = make_response(si.getvalue())
        output.headers["Content-Disposition"] = f"attachment; filename=estadisticas_{status}.csv"
        output.headers["Content-type"] = "text/csv"
        return output

    except Exception as e:
        return str(e), 500

# --- API: Obtener Historial de Checklists ---
@app.route('/api/checklists', methods=['GET'])
@login_required
def get_checklists():
    if not current_user.perm_checklist_acceso and current_user.role != 'Superusuario':
        return jsonify({'error': 'No autorizado'}), 403
    
    try:
        checklists = Checklist.query.order_by(Checklist.fecha.desc()).limit(100).all()
        results = []
        for c in checklists:
            fecha_utc = c.fecha.replace(tzinfo=pytz.utc)
            fecha_local = fecha_utc.astimezone(MEXICO_TZ)
            
            results.append({
                'id': c.id,
                'eco': c.numero_economico,
                'fecha': fecha_local.strftime('%d/%m/%Y %H:%M'),
                'usuario': c.user.username if c.user else 'Desconocido',
                'area': c.area.name if c.area else 'N/A',
                'tiene_extintor': c.tiene_extintor,
                'cantidad_extintores': c.cantidad_extintores,
                'fechas_extintores': c.fechas_extintores, 
                'tiene_corta_corriente': c.tiene_corta_corriente,
                'corta_corriente_funcional': c.corta_corriente_funcional,
                'tiene_aire': c.tiene_aire,
                'aire_funcional': c.aire_funcional
            })
            
        return jsonify(results)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# --- API: Eliminar Checklist (Permiso Granular) ---
@app.route('/api/checklists/<int:id>', methods=['DELETE'])
@login_required
def delete_checklist(id):
    if not current_user.perm_checklist_borrar and current_user.role != 'Superusuario':
        return jsonify({'error': 'No autorizado'}), 403
        
    try:
        checklist_item = db.session.get(Checklist, id)
        if not checklist_item:
            return jsonify({'error': 'Registro no encontrado'}), 404
            
        db.session.delete(checklist_item)
        db.session.commit()
        return jsonify({'message': 'Checklist eliminado'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# --- API: Editar Checklist (Permiso Granular) ---
@app.route('/api/checklists/<int:id>', methods=['PUT'])
@login_required
def edit_checklist(id):
    if not current_user.perm_checklist_editar and current_user.role != 'Superusuario':
        return jsonify({'error': 'No autorizado'}), 403
    
    data = request.json
    try:
        checklist_item = db.session.get(Checklist, id)
        if not checklist_item:
            return jsonify({'error': 'Registro no encontrado'}), 404

        def clean_int(val):
            if val is None or val == "": return None
            return int(val)
        def clean_bool(val):
            if val == "true" or val is True: return True
            return False

        if 'numero_economico' in data:
            checklist_item.numero_economico = data['numero_economico']
        if 'tiene_extintor' in data:
            checklist_item.tiene_extintor = clean_bool(data['tiene_extintor'])
        if 'cantidad_extintores' in data:
            checklist_item.cantidad_extintores = clean_int(data['cantidad_extintores'])
        if 'fechas_extintores' in data:
             if isinstance(data['fechas_extintores'], list):
                  checklist_item.fechas_extintores = ",".join(data['fechas_extintores'])
             else:
                  checklist_item.fechas_extintores = data['fechas_extintores']

        if 'tiene_corta_corriente' in data:
            checklist_item.tiene_corta_corriente = clean_bool(data['tiene_corta_corriente'])
        if 'corta_corriente_funcional' in data:
             if checklist_item.tiene_corta_corriente:
                  checklist_item.corta_corriente_funcional = clean_bool(data['corta_corriente_funcional'])
             else:
                  checklist_item.corta_corriente_funcional = None
            
        if 'tiene_aire' in data:
            checklist_item.tiene_aire = clean_bool(data['tiene_aire'])
        if 'aire_funcional' in data:
             if checklist_item.tiene_aire:
                  checklist_item.aire_funcional = clean_bool(data['aire_funcional'])
             else:
                  checklist_item.aire_funcional = None

        db.session.commit()
        return jsonify({'message': 'Checklist actualizado'}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# --- API: Descargar CSV de Checklist ---
@app.route('/api/checklist/download_csv', endpoint='download_checklist_csv')
@login_required
def download_checklist_csv():
    if not current_user.perm_checklist_acceso and current_user.role != 'Superusuario':
        return "No autorizado", 403
        
    try:
        checklists = Checklist.query.order_by(Checklist.fecha.desc()).all()
        si = io.StringIO()
        writer = csv.writer(si)
        
        headers = ['Fecha', 'Unidad', 'Usuario', 'Área', 'Extintor', 'Cant. Extintores', 'Vencimientos Extintores', 'Tiene Corta Corriente', 'Corta C. Funcional', 'Tiene A/C', 'A/C Funcional']
        writer.writerow(headers)
        
        for c in checklists:
            fecha_local = c.fecha.replace(tzinfo=pytz.utc).astimezone(MEXICO_TZ)
            writer.writerow([
                fecha_local.strftime('%d/%m/%Y %H:%M'), c.numero_economico, c.user.username if c.user else 'Desc.', c.area.name if c.area else 'N/A', "SÍ" if c.tiene_extintor else "NO", c.cantidad_extintores if c.tiene_extintor else "N/A", c.fechas_extintores if c.tiene_extintor else "N/A", "SÍ" if c.tiene_corta_corriente else "NO", "FUNCIONAL" if c.corta_corriente_funcional else "N/A", "SÍ" if c.tiene_aire else "NO", "FUNCIONAL" if c.aire_funcional else "N/A"
            ])

        output = make_response(si.getvalue())
        output.headers["Content-Disposition"] = "attachment; filename=reporte_checklist.csv"
        output.headers["Content-type"] = "text/csv"
        return output

    except Exception as e:
        return str(e), 500

# --- API: Guardar Checklist ---
@app.route('/api/checklist', methods=['POST'])
@login_required
def save_checklist():
    if not current_user.perm_checklist_crear and current_user.role != 'Superusuario':
        return jsonify({'error': 'No autorizado'}), 403
        
    data = request.json
    try:
        def clean_int(val):
            return int(val) if val else None
        def clean_bool(val):
            return True if val == "true" or val is True else False

        fechas_str = ""
        if data.get('fechas_extintores') and isinstance(data['fechas_extintores'], list):
            fechas_str = ",".join(data['fechas_extintores'])

        new_checklist = Checklist(
            numero_economico=data['numero_economico'],
            tiene_extintor=clean_bool(data.get('tiene_extintor')),
            cantidad_extintores=clean_int(data.get('cantidad_extintores')),
            fechas_extintores=fechas_str, 
            tiene_corta_corriente=clean_bool(data.get('tiene_corta_corriente')),
            corta_corriente_funcional=clean_bool(data.get('corta_corriente_funcional')) if data.get('tiene_corta_corriente') else None,
            tiene_aire=clean_bool(data.get('tiene_aire')),
            aire_funcional=clean_bool(data.get('aire_funcional')) if data.get('tiene_aire') else None,
            area_id=current_user.area_id,
            user_id=current_user.id
        )
        
        db.session.add(new_checklist)
        db.session.commit()
        return jsonify({'message': 'Checklist guardado correctamente'}), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f"Error al guardar: {str(e)}"}), 500


@app.route('/api/entradas', methods=['POST'])
@login_required
def registrar_entrada():
    if not current_user.perm_taller_registro and current_user.role != 'Superusuario':
        return jsonify({'error': 'No autorizado'}), 403
        
    data = request.json
    try:
        existe = TallerEntrada.query.filter_by(
            numero_economico=data['numero_economico'], 
            status='pendiente'
        ).first()
        if existe:
            return jsonify({'error': f"La unidad {data['numero_economico']} ya tiene un registro pendiente."}), 400

        fecha_entrada_manual = data.get('fecha_entrada_manual')
        
        if fecha_entrada_manual:
            dt_local = MEXICO_TZ.localize(datetime.strptime(fecha_entrada_manual, '%Y-%m-%d'))
            dt_local = dt_local.replace(hour=7, minute=0, second=0) 
            fecha_para_bd = dt_local.astimezone(pytz.utc)
        else:
            fecha_para_bd = datetime.utcnow()

        nueva_entrada = TallerEntrada(
            numero_economico=data['numero_economico'],
            tipo_vehiculo=data['tipo_vehiculo'],
            razones=data['motivo_de_entrada'], 
            otros_motivos=data.get('otros_motivos', '').strip(),
            dias_estimados=int(data['dias_estimados']),
            fecha_entrada=fecha_para_bd,
            area_id=current_user.area_id,
            user_id=current_user.id
        )
        db.session.add(nueva_entrada)
        db.session.commit()
        
        primera_nota = Nota(
            text=f"Entrada registrada por {current_user.username} con Motivo: {data['motivo_de_entrada']}",
            user_id=current_user.id,
            taller_entrada_id=nueva_entrada.id
        )
        db.session.add(primera_nota)
        
        otros_motivos = data.get('otros_motivos', '').strip()
        if otros_motivos:
            segunda_nota = Nota(
                text=f"Otros Motivos (al registrar): {otros_motivos}",
                user_id=current_user.id,
                taller_entrada_id=nueva_entrada.id
            )
            db.session.add(segunda_nota)
        
        db.session.commit()
        
        socketio.emit('cambio_detectado', {'message': 'Nueva entrada registrada'})
        return jsonify(nueva_entrada.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400

@app.route('/api/entradas/<int:id>/editar', methods=['PUT'])
@login_required
def editar_entrada(id):
    if not current_user.perm_taller_editar and current_user.role != 'Superusuario':
        return jsonify({'error': 'No autorizado'}), 403
    try:
        entrada = db.session.get(TallerEntrada, id)
        if not entrada:
            return jsonify({'error': 'Entrada no encontrada'}), 404
        
        # Validación de Área: Permite si el usuario es Global (None) o Superusuario
        if current_user.area_id is not None and entrada.area_id != current_user.area_id and current_user.role != 'Superusuario':
             return jsonify({'error': 'No autorizado para editar esta entrada'}), 403
        
        data = request.json
        cambios = []
        
        nuevos_dias = int(data.get('dias_estimados', entrada.dias_estimados))
        if nuevos_dias != entrada.dias_estimados:
            cambios.append(f"Días estimados cambiados de {entrada.dias_estimados} a {nuevos_dias}")
            entrada.dias_estimados = nuevos_dias
        
        nuevo_motivo = data.get('motivo_de_entrada', entrada.razones)
        if nuevo_motivo != entrada.razones:
            cambios.append(f"Motivo de entrada actualizado a: '{nuevo_motivo}'")
            entrada.razones = nuevo_motivo
            
        nuevos_otros_motivos = data.get('otros_motivos', entrada.otros_motivos)
        if nuevos_otros_motivos != entrada.otros_motivos:
            cambios.append(f"Otros Motivos actualizados a: '{nuevos_otros_motivos}'")
            entrada.otros_motivos = nuevos_otros_motivos

        if not cambios:
            return jsonify(entrada.to_dict())

        texto_nota = f"{current_user.username} actualizó la entrada: " + ", ".join(cambios) + "."
        nueva_nota = Nota(
            text=texto_nota,
            user_id=current_user.id,
            taller_entrada_id=id
        )
        db.session.add(nueva_nota)
        db.session.commit()
        
        socketio.emit('cambio_detectado', {'message': 'Entrada actualizada'})
        return jsonify(entrada.to_dict())
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/entradas/<int:id>/solicitar-revision', methods=['PUT'])
@login_required
def solicitar_revision(id):
    if not current_user.perm_taller_tecnico and current_user.role != 'Superusuario':
        return jsonify({'error': 'No autorizado'}), 403
        
    try:
        entrada = db.session.get(TallerEntrada, id)
        if not entrada:
            return jsonify({'error': 'Entrada no encontrada'}), 404

        # Validación de Área
        if current_user.area_id is not None and entrada.area_id != current_user.area_id and current_user.role != 'Superusuario':
             return jsonify({'error': 'No autorizado para completar esta entrada'}), 403

        entrada.status = 'en_revision'
        
        nota_cierre = Nota(
            text=f"Mantenimiento marcó como 'Completada'. Pendiente de autorización por Recepción.",
            user_id=current_user.id,
            taller_entrada_id=id
        )
        db.session.add(nota_cierre)
        db.session.commit()
        
        socketio.emit('cambio_detectado', {'message': 'Entrada enviada a revisión'})
        return jsonify(entrada.to_dict())
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/entradas/<int:id>/autorizar', methods=['PUT'])
@login_required
def autorizar_salida(id):
    if not current_user.perm_taller_autorizar and current_user.role != 'Superusuario':
        return jsonify({'error': 'No autorizado'}), 403
        
    try:
        entrada = db.session.get(TallerEntrada, id)
        if not entrada:
            return jsonify({'error': 'Entrada no encontrada'}), 404
        
        # Validación de Área
        if current_user.area_id is not None and entrada.area_id != current_user.area_id and current_user.role != 'Superusuario':
             return jsonify({'error': 'No autorizado para esta entrada'}), 403
        
        if entrada.status != 'en_revision':
            return jsonify({'error': 'Esta entrada no está pendiente de autorización'}), 400

        entrada.status = 'archivado'
        
        nota_final = Nota(
            text=f"{current_user.role} ({current_user.username}) autorizó la salida de la unidad.",
            user_id=current_user.id,
            taller_entrada_id=id
        )
        db.session.add(nota_final)
        db.session.commit()
        
        socketio.emit('cambio_detectado', {'message': 'Entrada autorizada y archivada'})
        return jsonify(entrada.to_dict())
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# --- API: Borrar Entradas (Solo Superusuario) ---
@app.route('/api/entradas/<int:id>', methods=['DELETE'])
@login_required
def delete_entrada(id):
    if current_user.role != 'Superusuario':
        return jsonify({'error': 'No autorizado'}), 403
        
    try:
        entrada = db.session.get(TallerEntrada, id)
        if not entrada:
            return jsonify({'error': 'Entrada no encontrada'}), 404
            
        Nota.query.filter_by(taller_entrada_id=id).delete()
        db.session.delete(entrada)
        db.session.commit()
        
        socketio.emit('cambio_detectado', {'message': 'Entrada eliminada por Superusuario'})
        return jsonify({'message': 'Entrada eliminada'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# --- APIs para el "Diario de Notas" ---

@app.route('/api/entradas/<int:id>/notas', methods=['GET'])
@login_required
def get_notas(id):
    try:
        entrada = db.session.get(TallerEntrada, id)
        
        if current_user.area_id is not None and entrada.area_id != current_user.area_id and current_user.role not in ['Gerente', 'Superusuario']:
            return jsonify({'error': 'No autorizado'}), 403
        
        notas = Nota.query.filter_by(taller_entrada_id=id).order_by(Nota.timestamp.asc()).all()
        
        results = []
        for n in notas:
            timestamp_utc = n.timestamp.replace(tzinfo=pytz.utc)
            timestamp_local = timestamp_utc.astimezone(MEXICO_TZ)
            results.append({
                'text': n.text,
                'timestamp': timestamp_local.strftime('%d/%m/%Y %H:%M'),
                'author': n.author.username if n.author else 'Sistema'
            })
        return jsonify(results)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/entradas/<int:id>/notas', methods=['POST'])
@login_required
def add_nota(id):
    if not current_user.perm_taller_editar and current_user.role != 'Superusuario':
        return jsonify({'error': 'No autorizado'}), 403

    try:
        data = request.json
        texto = data.get('text')
        if not texto:
            return jsonify({'error': 'El texto de la nota no puede estar vacío'}), 400
            
        entrada = db.session.get(TallerEntrada, id)
        
        if current_user.area_id is not None and entrada.area_id != current_user.area_id and current_user.role != 'Superusuario':
            return jsonify({'error': 'No autorizado'}), 403
        
        nueva_nota = Nota(text=texto, user_id=current_user.id, taller_entrada_id=id)
        db.session.add(nueva_nota)
        entrada.last_updated = datetime.utcnow()
        db.session.commit()
        
        socketio.emit('cambio_detectado', {'message': 'Nueva nota añadida'})
        return jsonify({'message': 'Nota añadida'}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# --- APIs para los Dropdowns de Recepción ---
@app.route('/api/areas')
@login_required
def get_areas():
    areas = Area.query.order_by(Area.name).all()
    return jsonify([{'id': a.id, 'name': a.name} for a in areas])

@app.route('/api/vehicles')
@login_required
def get_vehicles():
    if not current_user.perm_taller_registro and not current_user.perm_checklist_crear and current_user.role != 'Superusuario':
        return jsonify({'error': 'No autorizado'}), 403
    try:
        query_param = request.args.get('q', '')
        query = Vehicle.query.filter(Vehicle.name.ilike(f'%{query_param}%')).limit(20)
        vehicles = query.all()
        return jsonify([{'id': v.id, 'name': v.name} for v in vehicles])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# --- APIs del Panel de Administración ---

@app.route('/api/admin/areas', methods=['GET', 'POST'])
@login_required
def admin_areas():
    if current_user.role != 'Superusuario': return jsonify({'error': 'No autorizado'}), 403
    if request.method == 'GET': return jsonify([{'id': a.id, 'name': a.name} for a in Area.query.all()])
    nueva = Area(name=request.json['name'])
    db.session.add(nueva); db.session.commit(); return jsonify({'id': nueva.id, 'name': nueva.name}), 201

@app.route('/api/admin/users', methods=['GET', 'POST'])
@login_required
def admin_users():
    if current_user.role != 'Superusuario': return jsonify({'error': 'No autorizado'}), 403
    if request.method == 'GET': return jsonify([u.to_dict() for u in User.query.all()])
    data = request.json
    nuevo = User(username=data['username'], role=data.get('role', 'Usuario Base'), area_id=data.get('area_id'))
    nuevo.set_password(data['password'])
    p = data.get('perms', {})
    nuevo.perm_taller_acceso = p.get('taller_acceso', False)
    nuevo.perm_taller_registro = p.get('taller_registro', False)
    nuevo.perm_taller_editar = p.get('taller_editar', False)
    nuevo.perm_taller_autorizar = p.get('taller_autorizar', False)
    nuevo.perm_taller_tecnico = p.get('taller_tecnico', False)
    nuevo.perm_checklist_acceso = p.get('checklist_acceso', False)
    nuevo.perm_checklist_crear = p.get('checklist_crear', False)
    nuevo.perm_checklist_editar = p.get('checklist_editar', False)
    nuevo.perm_checklist_borrar = p.get('checklist_borrar', False)
    db.session.add(nuevo); db.session.commit(); return jsonify({'message': 'Usuario creado'}), 201

@app.route('/api/admin/users/<int:id>/permissions', methods=['PUT'])
@login_required
def update_user_permissions(id):
    if current_user.role != 'Superusuario': return jsonify({'error': 'No autorizado'}), 403
    data = request.json
    try:
        user = db.session.get(User, id)
        if not user: return jsonify({'error': 'Usuario no encontrado'}), 404
        
        perms = data.get('perms', {})
        
        # Actualización explícita para guardar los booleanos
        user.perm_taller_acceso = bool(perms.get('taller_acceso', user.perm_taller_acceso))
        user.perm_taller_registro = bool(perms.get('taller_registro', user.perm_taller_registro))
        user.perm_taller_editar = bool(perms.get('taller_editar', user.perm_taller_editar))
        user.perm_taller_autorizar = bool(perms.get('taller_autorizar', user.perm_taller_autorizar))
        user.perm_taller_tecnico = bool(perms.get('taller_tecnico', user.perm_taller_tecnico))
        user.perm_checklist_acceso = bool(perms.get('checklist_acceso', user.perm_checklist_acceso))
        user.perm_checklist_crear = bool(perms.get('checklist_crear', user.perm_checklist_crear))
        user.perm_checklist_editar = bool(perms.get('checklist_editar', user.perm_checklist_editar))
        user.perm_checklist_borrar = bool(perms.get('checklist_borrar', user.perm_checklist_borrar))
        
        db.session.commit()
        return jsonify({'message': 'Permisos actualizados correctamente'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/areas/<int:id>', methods=['DELETE'])
@login_required
def delete_area(id):
    if current_user.role != 'Superusuario': return jsonify({'error': 'No autorizado'}), 403
    try:
        area = db.session.get(Area, id)
        if not area: return jsonify({'error': 'Área no encontrada'}), 404
        user_existe = User.query.filter_by(area_id=id).first()
        if user_existe: return jsonify({'error': f'No se puede eliminar: el usuario {user_existe.username} pertenece a esta área.'}), 400
        entrada_existe = TallerEntrada.query.filter_by(area_id=id).first()
        if entrada_existe: return jsonify({'error': f'No se puede eliminar: hay entradas de taller asignadas a esta área.'}), 400
        db.session.delete(area); db.session.commit(); return jsonify({'message': f'Área {area.name} eliminada'})
    except Exception as e:
        db.session.rollback(); return jsonify({'error': str(e)}), 500

@app.route('/api/admin/users/<int:id>/reset-password', methods=['PUT'])
@login_required
def reset_user_password(id):
    if current_user.role != 'Superusuario': return jsonify({'error': 'No autorizado'}), 403
    data = request.json
    if not data.get('password'): return jsonify({'error': 'La nueva contraseña no puede estar vacía'}), 400
    user = db.session.get(User, id)
    if not user: return jsonify({'error': 'Usuario no encontrado'}), 404
    user.set_password(data['password'])
    db.session.commit(); return jsonify({'message': f'Contraseña para {user.username} actualizada'})

@app.route('/api/admin/users/<int:id>', methods=['DELETE'])
@login_required
def delete_user(id):
    if current_user.role != 'Superusuario': return jsonify({'error': 'No autorizado'}), 403
    if id == current_user.id: return jsonify({'error': 'No puedes eliminarte a ti mismo'}), 400
    user = db.session.get(User, id)
    if not user: return jsonify({'error': 'Usuario no encontrado'}), 404
    try:
        TallerEntrada.query.filter_by(user_id=id).update({'user_id': None})
        Checklist.query.filter_by(user_id=id).update({'user_id': None})
        Nota.query.filter_by(user_id=id).update({'user_id': None})
        db.session.commit() 
        db.session.delete(user); db.session.commit()
        return jsonify({'message': f'Usuario {user.username} eliminado.'})
    except Exception as e:
        db.session.rollback(); return jsonify({'error': f'No se pudo eliminar: {str(e)}'}), 500


# =======================================================
# ---    Comandos de Terminal (Para inicializar)      ---
# =======================================================

@app.cli.command("db-create")
def db_create():
    db.create_all()
    print("Base de datos y tablas creadas.")

@app.cli.command("create-data")
def create_data():
    try:
        db.session.query(Checklist).delete()
        db.session.query(Nota).delete()
        db.session.query(TallerEntrada).delete()
        db.session.query(User).delete()
        db.session.query(Area).delete()
        db.session.commit()
        print("Tablas limpiadas.")

        area1 = Area(name="Salamanca")
        area2 = Area(name="Laredo")
        db.session.add_all([area1, area2])
        db.session.commit()
        print("Áreas creadas: Salamanca, Laredo")
        
        user_r_sal = User(username='recepcion_sal', role='Recepcion', area_id=area1.id)
        user_r_sal.set_password('pass123')
        user_r_sal.perm_taller_acceso = True
        user_r_sal.perm_taller_registro = True
        user_r_sal.perm_taller_editar = True
        user_r_sal.perm_taller_autorizar = True
        user_r_sal.perm_checklist_acceso = True
        user_r_sal.perm_checklist_crear = True
        
        user_m_sal = User(username='manto_sal', role='Mantenimiento', area_id=area1.id)
        user_m_sal.set_password('pass123')
        user_m_sal.perm_taller_acceso = True
        user_m_sal.perm_taller_tecnico = True
        user_m_sal.perm_checklist_acceso = True
        
        user_gerente = User(username='gerente', role='Gerente', area_id=None)
        user_gerente.set_password('pass123')
        user_gerente.perm_taller_acceso = True
        user_gerente.perm_checklist_acceso = True
        
        user_super = User(username='superusuario', role='Superusuario', area_id=None)
        user_super.set_password('pass1key')

        db.session.add_all([user_r_sal, user_m_sal, user_gerente, user_super])
        db.session.commit()
        print("Datos iniciales creados con permisos.")
    except Exception as e:
        db.session.rollback()
        print(f"Error al crear datos: {e}")

# --- COMANDO SYNC: Identificación Inteligente de Tractos y Remolques ---
@app.cli.command("sync-vehicles")
def sync_vehicles():
    """Sincroniza Vehicles y Trailers de Samsara y los clasifica comparando etiquetas con áreas de la plataforma."""
    SAMSARA_TOKEN = os.environ.get("SAMSARA_API_TOKEN")
    HEADERS = {'Authorization': f'Bearer {SAMSARA_TOKEN}'}
    # Lista de endpoints para barrer ambos tipos de unidades
    ENDPOINTS = [
        ("Vehículos", "https://api.samsara.com/fleet/vehicles"),
        ("Remolques", "https://api.samsara.com/fleet/trailers")
    ]
    
    if not SAMSARA_TOKEN:
        print("Error: SAMSARA_API_TOKEN no encontrado en .env")
        return
        
    try:
        areas_plataforma = [a.name.upper() for a in Area.query.all()]
        print(f"Iniciando sincronización dual avanzada... Áreas detectadas: {areas_plataforma}")

        unidades_en_bd = {v.samsara_id: v for v in Vehicle.query.all()}
        contador_nuevos = 0
        contador_actualizados = 0
        
        for tipo, url in ENDPOINTS:
            print(f"Barrido completo de {tipo}...")
            has_next_page = True
            after_cursor = None
            
            while has_next_page:
                params = {'limit': 500}
                if after_cursor:
                    params['after'] = after_cursor
                
                response = requests.get(url, headers=HEADERS, params=params)
                response.raise_for_status()
                json_data = response.json()
                items_samsara = json_data.get('data', [])
                
                if not items_samsara:
                    break
                
                for item in items_samsara:
                    s_id = item['id']
                    s_name = item['name']
                    tags = [t['name'] for t in item.get('tags', [])]
                    
                    operacion = "Sin Operación"
                    found_match = False
                    
                    for t_name in tags:
                        t_clean = re.sub(r'\s+rastreos\s+principales', '', t_name, flags=re.IGNORECASE).strip()
                        if t_clean.upper() in areas_plataforma:
                            operacion = t_clean
                            found_match = True
                            break
                    
                    if not found_match and tags:
                        operacion = re.sub(r'\s+rastreos\s+principales', '', tags[0], flags=re.IGNORECASE).strip()

                    if s_id not in unidades_en_bd:
                        nueva_unidad = Vehicle(samsara_id=s_id, name=s_name, operation=operacion)
                        db.session.add(nueva_unidad)
                        contador_nuevos += 1
                    else:
                        unidades_en_bd[s_id].name = s_name
                        unidades_en_bd[s_id].operation = operacion
                        contador_actualizados += 1
                
                pagination = json_data.get('pagination', {})
                has_next_page = pagination.get('hasNextPage', False)
                if has_next_page:
                    after_cursor = pagination.get('endCursor')
        
        db.session.commit()
        print(f"Sincronización exhaustiva finalizada. Nuevos: {contador_nuevos}, Actualizados: {contador_actualizados}.")
    except Exception as e:
        db.session.rollback()
        print(f"Error fatal en sincronización: {e}")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=True, allow_unsafe_werkzeug=True)