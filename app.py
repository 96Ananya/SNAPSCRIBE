from flask import Flask, render_template, request, send_file, flash, redirect, url_for
import os
from PIL import Image
import zipfile
import io
import requests
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB

OCR_API_KEY = "K88475158488957"
OCR_API_URL = "https://api.ocr.space/parse/image"  # Example OCR API endpoint

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)


@app.route('/')
def index():
    return render_template('index.html')


# -------------------- Image Splitting --------------------
@app.route('/split', methods=['POST'])
def split_image():
    if 'image' not in request.files:
        flash('No file part')
        return redirect(request.url)

    file = request.files['image']
    rows = int(request.form.get('rows', 1))
    cols = int(request.form.get('cols', 1))

    if file.filename == '':
        flash('No selected file')
        return redirect(request.url)

    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)

    try:
        img = Image.open(filepath)
    except Exception as e:
        flash(f"Error opening image: {e}")
        return redirect(request.url)

    img_width, img_height = img.size
    tile_width = img_width // cols
    tile_height = img_height // rows

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
        for r in range(rows):
            for c in range(cols):
                left = c * tile_width
                upper = r * tile_height
                right = (c + 1) * tile_width
                lower = (r + 1) * tile_height
                tile = img.crop((left, upper, right, lower))

                tile_bytes = io.BytesIO()
                tile.save(tile_bytes, format='PNG')
                tile_bytes.seek(0)
                zip_file.writestr(f"tile_r{r+1}_c{c+1}.png", tile_bytes.read())

    zip_buffer.seek(0)
    return send_file(zip_buffer, as_attachment=True, download_name='tiles.zip', mimetype='application/zip')


# -------------------- OCR using Cloud API --------------------
@app.route('/ocr', methods=['POST'])
def ocr():
    if 'image' not in request.files:
        flash('No file part')
        return redirect(request.url)

    file = request.files['image']
    if file.filename == '':
        flash('No selected file')
        return redirect(request.url)

    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)

    # Send to OCR API
    with open(filepath, 'rb') as f:
        result = requests.post(
            OCR_API_URL,
            files={'filename': f},
            data={'apikey': OCR_API_KEY, 'language': 'eng'}
        )
    result_json = result.json()
    try:
        text = result_json['ParsedResults'][0]['ParsedText']
    except (KeyError, IndexError):
        text = "OCR failed. Please try again."

    return render_template('ocr_results.html', text=text)


# -------------------- Download extracted text --------------------
@app.route('/download_text', methods=['POST'])
def download_text():
    text = request.form['text']
    return send_file(
        io.BytesIO(text.encode()),
        as_attachment=True,
        download_name='extracted_text.txt',
        mimetype='text/plain'
    )


if __name__ == '__main__':
    app.run(debug=True)
