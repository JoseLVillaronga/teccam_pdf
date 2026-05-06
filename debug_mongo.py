from pymongo import MongoClient
from dotenv import load_dotenv
import os
import sys

# Cargar variables de entorno
load_dotenv()

user = os.getenv('MONGO_USER')
password = os.getenv('MONGO_PASS')
host = os.getenv('MONGO_HOST')

print(f"Intentando conectar a MongoDB...")
print(f"Host: {host}")
print(f"Usuario: {user}")

# Construir URI
mongo_uri = f"mongodb://{user}:{password}@{host}"

try:
    # timeoutMS=5000 para que no se quede colgado si no conecta
    client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
    
    # El comando 'ping' verifica si el servidor es accesible y las credenciales son correctas
    client.admin.command('ping')
    print("✅ ¡Conexión exitosa a MongoDB!")
    
    # Listar bases de datos para confirmar permisos
    dbs = client.list_database_names()
    print(f"Bases de datos disponibles: {dbs}")
    
except Exception as e:
    print(f"❌ Error al conectar a MongoDB: {e}")
    
    print("\nSugerencias:")
    if "Authentication failed" in str(e):
        print("- Verifica que el usuario y la contraseña sean correctos.")
        print("- Prueba añadiendo '?authSource=admin' al final de la URI si el usuario está en la base 'admin'.")
    elif "connection closed" in str(e) or "Timeout" in str(e):
        print("- Verifica que el host sea correcto y que MongoDB esté escuchando en ese puerto.")
        print("- Si usas 'localhost', asegúrate de que no haya firewalls bloqueando el puerto 27017.")
