from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

import fitz  # PyMuPDF
from flask import Flask, jsonify, render_template_string, request, send_file
from PIL import Image

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB

HTML_PAGE = """
<!doctype html>
<html lang="es">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>pdf2eps</title>
  <style>
    :root {
      --bg: #f7f4ec;
      --card: #ffffff;
      --ink: #1f2430;
      --accent: #bd7b30;
      --accent-dark: #8f5617;
      --border: #e8ddcc;
      --muted: #5f6778;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      font-family: "Avenir Next", "Segoe UI", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at 10% 10%, #fff7dc 0%, transparent 30%),
        radial-gradient(circle at 90% 20%, #f6d8b7 0%, transparent 35%),
        var(--bg);
      display: grid;
      place-items: center;
      padding: 24px;
    }
    .card {
      width: min(680px, 100%);
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 18px;
      padding: 28px;
      box-shadow: 0 12px 40px rgba(58, 42, 16, 0.12);
      animation: rise 420ms ease-out;
    }
    @keyframes rise {
      from { opacity: 0; transform: translateY(8px); }
      to { opacity: 1; transform: translateY(0); }
    }
    h1 {
      margin: 0 0 8px 0;
      font-size: clamp(1.6rem, 3vw, 2.2rem);
      letter-spacing: 0.02em;
    }
    p { margin: 0 0 20px 0; color: var(--muted); }
    form { display: grid; gap: 14px; }
    input[type="file"] {
      border: 1px dashed var(--border);
      border-radius: 12px;
      background: #fffdfa;
      padding: 14px;
      font-size: 1rem;
    }
    button {
      border: 0;
      border-radius: 12px;
      background: linear-gradient(135deg, var(--accent), #d89f55);
      color: #fff;
      font-size: 1rem;
      font-weight: 700;
      padding: 12px 18px;
      cursor: pointer;
      transition: transform 120ms ease, background 120ms ease;
    }
    button:hover { transform: translateY(-1px); background: linear-gradient(135deg, var(--accent-dark), #b5712e); }
    button:disabled { opacity: 0.65; cursor: wait; transform: none; }
    .status {
      min-height: 1.5em;
      font-size: 0.95rem;
      color: var(--muted);
    }
    .status.error { color: #9f2f2f; }
    .hint { margin-top: 4px; font-size: 0.85rem; color: var(--muted); }
  </style>
</head>
<body>
  <main class="card">
    <h1>pdf2eps</h1>
    <p>Sube un archivo PDF y descarga su conversión en EPS.</p>
    <form id="upload-form">
      <input id="pdf-file" type="file" name="pdf_file" accept="application/pdf,.pdf" required />
      <button id="submit-btn" type="submit">Convertir a EPS</button>
    </form>
    <div id="status" class="status"></div>
    <div class="hint">Si tu PDF tiene varias páginas, se descargará un ZIP con un EPS por página.</div>
  </main>
    <div id="copyright">
    <p>&copy; 2026, <a href="https://isantosruiz.github.io/home/" style="text-decoration: none;">Ildeberto de los Santos Ruiz</a></p>
  </div>

  <script>
    const form = document.getElementById("upload-form");
    const input = document.getElementById("pdf-file");
    const button = document.getElementById("submit-btn");
    const statusEl = document.getElementById("status");

    function setStatus(message, isError = false) {
      statusEl.textContent = message;
      statusEl.classList.toggle("error", isError);
    }

    function getFilename(contentDisposition, fallback) {
      if (!contentDisposition) return fallback;
      const utf8Match = contentDisposition.match(/filename\\*=UTF-8''([^;]+)/i);
      if (utf8Match?.[1]) {
        return decodeURIComponent(utf8Match[1]);
      }
      const basicMatch = contentDisposition.match(/filename="?([^"]+)"?/i);
      if (basicMatch?.[1]) {
        return basicMatch[1];
      }
      return fallback;
    }

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const file = input.files?.[0];
      if (!file) {
        setStatus("Selecciona un PDF antes de continuar.", true);
        return;
      }

      const body = new FormData();
      body.append("pdf_file", file);

      button.disabled = true;
      setStatus("Convirtiendo archivo, espera unos segundos...");

      try {
        const response = await fetch("/convert", { method: "POST", body });
        if (!response.ok) {
          let message = "No se pudo completar la conversión.";
          try {
            const errorJson = await response.json();
            if (errorJson?.error) message = errorJson.error;
          } catch (_) {}
          throw new Error(message);
        }

        const blob = await response.blob();
        const contentDisposition = response.headers.get("Content-Disposition");
        const fallbackName = file.name.toLowerCase().endsWith(".pdf")
          ? file.name.slice(0, -4) + ".eps"
          : "converted.eps";
        const filename = getFilename(contentDisposition, fallbackName);

        const url = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = filename;
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
        URL.revokeObjectURL(url);

        setStatus("Conversión completada. Descarga iniciada.");
      } catch (error) {
        setStatus(error.message || "Ocurrió un error inesperado.", true);
      } finally {
        button.disabled = false;
      }
    });
  </script>
</body>
</html>
"""


@app.get("/")
def home():
    return render_template_string(HTML_PAGE)


@app.post("/convert")
def convert_pdf_to_eps():
    pdf_file = request.files.get("pdf_file")
    if pdf_file is None or pdf_file.filename == "":
        return jsonify({"error": "No se recibió un archivo PDF."}), 400

    if not pdf_file.filename.lower().endswith(".pdf"):
        return jsonify({"error": "El archivo debe tener extensión .pdf."}), 400

    safe_name = Path(pdf_file.filename).name
    base_name = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(safe_name).stem) or "converted"

    try:
        source = io.BytesIO(pdf_file.read())
        doc = fitz.open(stream=source.getvalue(), filetype="pdf")
    except Exception:
        return jsonify({"error": "El PDF parece estar dañado o no es válido."}), 400

    if doc.page_count == 0:
        doc.close()
        return jsonify({"error": "El PDF no contiene páginas."}), 400

    try:
        eps_pages: list[tuple[str, bytes]] = []
        for page_index in range(doc.page_count):
            page = doc.load_page(page_index)
            pixmap = page.get_pixmap(dpi=300, alpha=False)
            image = Image.frombytes("RGB", [pixmap.width, pixmap.height], pixmap.samples)

            eps_buffer = io.BytesIO()
            image.save(eps_buffer, format="EPS")
            eps_pages.append((f"{base_name}_page_{page_index + 1}.eps", eps_buffer.getvalue()))
    except Exception:
        return jsonify({"error": "Ocurrió un error al convertir el PDF a EPS."}), 500
    finally:
        doc.close()

    if len(eps_pages) == 1:
        filename, content = eps_pages[0]
        return send_file(
            io.BytesIO(content),
            as_attachment=True,
            download_name=filename,
            mimetype="application/postscript",
        )

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zip_file:
        for filename, content in eps_pages:
            zip_file.writestr(filename, content)

    zip_buffer.seek(0)
    return send_file(
        zip_buffer,
        as_attachment=True,
        download_name=f"{base_name}_eps.zip",
        mimetype="application/zip",
    )


# Vercel looks for `app` in api/*.py
