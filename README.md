# pdf2eps

Aplicación web en Python para convertir PDF a EPS y descargar el resultado.

## Desarrollo local

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
flask --app app.py --debug run
```

Abrir `http://127.0.0.1:5000`.

## Despliegue en Vercel

1. Crear un proyecto nuevo en Vercel apuntando a este repositorio.
2. Vercel instalará dependencias desde `requirements.txt`.
3. Vercel detecta el preset Flask y usa `app.py` como entrada.

## Notas

- Si el PDF tiene una sola página, se descarga un `.eps`.
- Si tiene varias páginas, se descarga un `.zip` con un EPS por página.
