from flask import Flask, render_template, request, send_file, flash, redirect, url_for
import os
from PIL import Image
import zipfile
import io
import requests
from werkzeug.utils import secure_filename

app = Flask(__name__)
# Use a simple secret key for local/testing. In production, store this in an environment variable.
app.secret_key = 'snap_scribe_secret_2025'

app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB max upload

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# OCR.Space API key (as requested inserted directly)
OCR_API_KEY = "K88475158488957"

# Allowed image extensions
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp'}


def allowed_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route('/')
def index():
    return render_template('index.html')


# ---------------- Image Splitter ----------------
@app.route('/split', methods=['POST'])
def split_image():
    if 'file' not in request.files:
        flash('No file uploaded.')
        return redirect(request.url)

    file = request.files['file']
    if file.filename == '':
        flash('No file selected.')
        return redirect(request.url)

    if not (file and allowed_file(file.filename)):
        flash('Invalid file type. Only images allowed.')
        return redirect(url_for('index'))

    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)

    # Get rows and cols
    try:
        rows = int(request.form.get('rows', 1))
        cols = int(request.form.get('cols', 1))
        if rows <= 0 or cols <= 0:
            raise ValueError
    except ValueError:
        flash('Invalid rows/columns. Must be positive integers.')
        os.remove(filepath)
        return redirect(url_for('index'))

    try:
        with Image.open(filepath) as img:
            width, height = img.size
            cell_width = width // cols
            cell_height = height // rows

            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for r in range(rows):
                    for c in range(cols):
                        left = c * cell_width
                        top = r * cell_height
                        right = left + cell_width
                        bottom = top + cell_height

                        split_img = img.crop((left, top, right, bottom))
                        split_filename = f"split_{r+1}_{c+1}.png"

                        img_buffer = io.BytesIO()
                        split_img.save(img_buffer, format='PNG')
                        img_buffer.seek(0)
                        zipf.writestr(split_filename, img_buffer.getvalue())

            zip_buffer.seek(0)
    except Exception as e:
        flash(f"Image processing failed: {e}")
        os.remove(filepath)
        return redirect(url_for('index'))

    # cleanup and send zip
    os.remove(filepath)
    return send_file(
        zip_buffer,
        mimetype='application/zip',
        as_attachment=True,
        download_name='split_images.zip'
    )


# ---------------- OCR using OCR.Space ----------------
@app.route('/ocr', methods=['POST'])
def ocr_image():
    if 'file' not in request.files:
        flash('No file uploaded.')
        return redirect(request.url)

    file = request.files['file']
    if file.filename == '':
        flash('No file selected.')
        return redirect(request.url)

    if not (file and allowed_file(file.filename)):
        flash('Invalid file type. Only images allowed.')
        return redirect(url_for('index'))

    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)

    # Save and optionally resize to keep uploads reasonable for OCR API
    try:
        img = Image.open(file.stream).convert('RGB')
        MAX_SIDE = 2000  # reduce very large images; keeps file small & faster OCR
        img.thumbnail((MAX_SIDE, MAX_SIDE))
        img.save(filepath, format='JPEG', quality=85)
    except Exception as e:
        flash(f"Failed to read/prepare image: {e}")
        return redirect(url_for('index'))

    # Call OCR.Space API
    try:
        with open(filepath, 'rb') as f:
            files = {'file': (filename, f, 'image/jpeg')}
            data = {
                'apikey': OCR_API_KEY,
                'language': 'eng',
                'isOverlayRequired': False,
                'OCREngine': 2  # engine 2 is newer; you can remove if not supported
            }
            response = requests.post("https://api.ocr.space/parse/image", files=files, data=data, timeout=60)

        result = response.json()
    except requests.exceptions.RequestException as re:
        os.remove(filepath)
        flash(f"OCR request failed: {re}")
        return redirect(url_for('index'))
    except Exception as e:
        os.remove(filepath)
        flash(f"OCR failed: {e}")
        return redirect(url_for('index'))

    # Parse OCR result
    try:
        if result.get('IsErroredOnProcessing'):
            # ErrorMessage might be a list or string
            err = result.get('ErrorMessage') or result.get('ErrorDetails') or 'Unknown OCR error'
            # If list, join
            if isinstance(err, list):
                err = ' | '.join(err)
            raise Exception(err)

        parsed = result.get('ParsedResults')
        if not parsed or len(parsed) == 0:
            raise Exception('No text found in OCR response.')

        extracted_text = parsed[0].get('ParsedText', '').strip()
        if not extracted_text:
            extracted_text = "No text detected. Try a clearer image or crop to the text area."
    except Exception as e:
        os.remove(filepath)
        flash(f"OCR failed: {e}")
        return redirect(url_for('index'))

    # Clean up and render result
    os.remove(filepath)
    return render_template('ocr_result.html', text=extracted_text)


# ---------------- Download TXT ----------------
@app.route('/download_text', methods=['POST'])
def download_text():
    text = request.form.get('text', '')
    txt_buffer = io.BytesIO()
    txt_buffer.write(text.encode('utf-8'))
    txt_buffer.seek(0)

    return send_file(
        txt_buffer,
        mimetype='text/plain',
        as_attachment=True,
        download_name='extracted_text.txt'
    )


if __name__ == '__main__':
    # debug=True for local testing. Turn off in production.
    app.run(debug=True)
