from pymongo import MongoClient
from dotenv import load_dotenv
import os

# Cargar variables de entorno
load_dotenv()

user = os.getenv('MONGO_USER')
password = os.getenv('MONGO_PASS')
host = os.getenv('MONGO_HOST')

# Prueba 1: Sin authSource (Lo que hace app.py actualmente)
print("--- Prueba 1: Sin authSource ---")
uri1 = f"mongodb://{user}:{password}@{host}"
client1 = MongoClient(uri1, serverSelectionTimeoutMS=2000)
try:
    # Intentar acceder a la base de datos específica
    print(f"Intentando acceder a 'teccam_pdf'...")
    client1.teccam_pdf.command('ping')
    print("✅ Prueba 1 exitosa")
except Exception as e:
    print(f"❌ Prueba 1 falló: {e}")

# Prueba 2: Con authSource=admin
print("\n--- Prueba 2: Con authSource=admin ---")
uri2 = f"mongodb://{user}:{password}@{host}/?authSource=admin"
client2 = MongoClient(uri2, serverSelectionTimeoutMS=2000)
try:
    print(f"Intentando acceder a 'teccam_pdf' con authSource=admin...")
    client2.teccam_pdf.command('ping')
    print("✅ Prueba 2 exitosa")
except Exception as e:
    print(f"❌ Prueba 2 falló: {e}")
