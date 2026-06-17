# Pasos para Instalar y Compartir el Sistema en el Servidor de la Oficina

Sigue esta guía paso a paso dentro del servidor de tu trabajo (**192.168.30.42**) usando la conexión a Escritorio Remoto:

---

### Paso 1: Descargar el Código en el Servidor
1. Entra por Escritorio Remoto a tu servidor `192.168.30.42`.
2. Abre el navegador web dentro del servidor y ve a:
   [https://github.com/Jesusrangel3/RoyalMantenimiento](https://github.com/Jesusrangel3/RoyalMantenimiento)
3. Haz clic en el botón verde **Code** y selecciona **Download ZIP** (o clónalo si tienen Git instalado).
4. Descomprime la carpeta en una ubicación permanente del servidor, por ejemplo: `C:\RoyalMantenimiento`.

---

### Paso 2: Instalar Python en el Servidor
1. Si el servidor no tiene Python, descárgalo e instálalo desde [python.org](https://www.python.org/downloads/) (versión recomendada: 3.10 o 3.11).
2. Durante la instalación, marca la casilla **"Add Python to PATH"** (Agregar Python al PATH).

---

### Paso 3: Crear el Archivo de Configuración (.env)
Dentro de la carpeta `C:\RoyalMantenimiento` en el servidor, crea un archivo de texto con el nombre `.env` y pega este contenido:
```env
# Conexión local a la base de datos SQL Server
DATABASE_URL=mssql+pymssql://analista_cif:Royal2025@localhost/RoyalCIF

# Clave de seguridad (puedes inventar una larga)
SECRET_KEY=clave-secreta-para-sesiones-de-taller

# Puerto de escucha
PORT=5000
FLASK_ENV=production
```

---

### Paso 4: Instalar las Librerías
Abre la consola de comandos (**CMD** o **PowerShell**) en el servidor como Administrador, muévete a la carpeta y ejecuta:
```cmd
cd C:\RoyalMantenimiento
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

---

### Paso 5: Crear la Estructura en la Base de Datos
En la misma consola (con el entorno virtual activo), ejecuta este comando para crear las tablas de taller en tu SQL Server y poblar los usuarios de prueba:
```cmd
python -m flask create-data
```
*Esto creará automáticamente los usuarios: `recepcion_sal` (contraseña `pass123`) y `dev_admin` (contraseña `devpass123`) en la base de datos `RoyalCIF` de tu servidor.*

---

### Paso 6: Arrancar el Sistema en Producción (Compartir)
Para que el sistema corra de forma permanente en la red de tu oficina y fuera de ella:

1. **Habilitar el puerto en IIS:**
   El administrador de sistemas de tu empresa debe configurar **IIS (Internet Information Services)** en el servidor para que apunte a `C:\RoyalMantenimiento` y redirija el tráfico web a la aplicación de Flask usando *HttpPlatformHandler*.
2. **Abrir el puerto en el módem:**
   El administrador abrirá el puerto de internet (por ejemplo, el `80` o `443` para HTTPS) en el módem/firewall de tu oficina apuntando a la IP `192.168.30.42` de tu servidor.
3. **¡Listo para usar!**
   Una vez configurado, las personas fuera de la oficina ingresarán usando la dirección pública o dominio que les asigne tu administrador de sistemas.
