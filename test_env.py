from dotenv import load_dotenv
import os

load_dotenv()

# Imprimir todas las variables de entorno
for key, value in os.environ.items():
    print(f"{key}: {value}")
