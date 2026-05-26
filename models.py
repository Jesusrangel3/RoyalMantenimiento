from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
import pytz
from datetime import datetime

db = SQLAlchemy()
MEXICO_TZ = pytz.timezone('America/Mexico_City')

class Area(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    users = db.relationship('User', backref='area', lazy=True)
    entradas = db.relationship('TallerEntrada', backref='area', lazy=True)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(256))
    role = db.Column(db.String(50), nullable=False) # Recepcion, Mantenimiento, Gerente, Superusuario
    area_id = db.Column(db.Integer, db.ForeignKey('area.id'), nullable=True)

    # --- Permisos Granulares ---
    perm_taller_acceso = db.Column(db.Boolean, default=False)
    perm_taller_registro = db.Column(db.Boolean, default=False)
    perm_taller_editar = db.Column(db.Boolean, default=False)
    perm_taller_autorizar = db.Column(db.Boolean, default=False)
    perm_taller_tecnico = db.Column(db.Boolean, default=False)

    perm_checklist_acceso = db.Column(db.Boolean, default=False)
    perm_checklist_crear = db.Column(db.Boolean, default=False)
    perm_checklist_editar = db.Column(db.Boolean, default=False)
    perm_checklist_borrar = db.Column(db.Boolean, default=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'role': self.role,
            'area_id': self.area_id,
            'area_name': self.area.name if self.area else 'Global',
            'perms': {
                'taller_acceso': self.perm_taller_acceso,
                'taller_registro': self.perm_taller_registro,
                'taller_editar': self.perm_taller_editar,
                'taller_autorizar': self.perm_taller_autorizar,
                'taller_tecnico': self.perm_taller_tecnico,
                'checklist_acceso': self.perm_checklist_acceso,
                'checklist_crear': self.perm_checklist_crear,
                'checklist_editar': self.perm_checklist_editar,
                'checklist_borrar': self.perm_checklist_borrar
            }
        }

class Vehicle(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    samsara_id = db.Column(db.String(100), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    operation = db.Column(db.String(200), nullable=True)

class TallerEntrada(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    numero_economico = db.Column(db.String(50), nullable=False)
    tipo_vehiculo = db.Column(db.String(50), nullable=False)
    razones = db.Column(db.String(500), nullable=False) 
    otros_motivos = db.Column(db.String(500), nullable=True)
    dias_estimados = db.Column(db.Integer, nullable=False, default=1)
    fecha_entrada = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='pendiente') # pendiente, en_revision, archivado
    last_updated = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    area_id = db.Column(db.Integer, db.ForeignKey('area.id'), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    
    notas = db.relationship('Nota', backref='entrada', lazy=True, cascade="all, delete-orphan")

    def to_dict(self):
        fecha_entrada_local = self.fecha_entrada.replace(tzinfo=pytz.utc).astimezone(MEXICO_TZ)
        last_updated_local = self.last_updated.replace(tzinfo=pytz.utc).astimezone(MEXICO_TZ)
        
        dias_en_base = (datetime.now(MEXICO_TZ).date() - fecha_entrada_local.date()).days
        if dias_en_base <= 0: dias_en_base = 1
        
        excedido = 0
        if dias_en_base > self.dias_estimados:
            excedido = dias_en_base - self.dias_estimados
            
        lista_razones = [r.strip() for r in self.razones.split(',') if r.strip()] if self.razones else []
        
        return {
            'id': self.id,
            'numero_economico': self.numero_economico,
            'tipo_vehiculo': self.tipo_vehiculo,
            'razones': lista_razones,
            'otros_motivos': self.otros_motivos,
            'dias_estimados': self.dias_estimados,
            'fecha_entrada_str': fecha_entrada_local.strftime('%d/%m/%Y %H:%M'),
            'last_updated_str': last_updated_local.strftime('%d/%m/%Y %H:%M'),
            'dias_en_taller': dias_en_base,
            'excedido_por': excedido,
            'status': self.status,
            'area_name': self.area.name if self.area else 'N/A'
        }

class Nota(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    taller_entrada_id = db.Column(db.Integer, db.ForeignKey('taller_entrada.id'), nullable=False)
    
    author = db.relationship('User', backref='notas')

class Checklist(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    numero_economico = db.Column(db.String(50), nullable=False)
    fecha = db.Column(db.DateTime, default=datetime.utcnow)
    
    tiene_extintor = db.Column(db.Boolean, default=False)
    cantidad_extintores = db.Column(db.Integer, nullable=True)
    fechas_extintores = db.Column(db.String(250), nullable=True)
    
    tiene_corta_corriente = db.Column(db.Boolean, default=False)
    corta_corriente_funcional = db.Column(db.Boolean, nullable=True)
    
    tiene_aire = db.Column(db.Boolean, default=False)
    aire_funcional = db.Column(db.Boolean, nullable=True)
    
    area_id = db.Column(db.Integer, db.ForeignKey('area.id'), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    
    area = db.relationship('Area')
    user = db.relationship('User')