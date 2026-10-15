from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from urllib.parse import urlparse

UPLOAD_DIR = Path(__file__).resolve().parent / "uploads"
MAX_REQUEST_SIZE = 100 * 1024 * 1024
HOST, PORT = "127.0.0.1", 8765

PAGE = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>File Inbox</title>
<style>
:root{font-family:Georgia,'Times New Roman',serif;color:#202a27;background:#f4f6f2}
*{box-sizing:border-box}body{min-height:100vh;margin:0;padding:48px 20px;background-image:radial-gradient(#c8d1c8 .7px,transparent .7px);background-size:18px 18px}
main{width:min(680px,100%);margin:auto}header{margin-bottom:30px}.eyebrow{margin:0 0 12px;color:#bf4f34;font:700 12px 'Trebuchet MS',sans-serif;text-transform:uppercase}
h1{margin:0;font-size:clamp(34px,8vw,54px);font-weight:500;line-height:1.04}.lede{max-width:440px;margin:14px 0 0;color:#5d6963;font:15px/1.6 'Trebuchet MS',sans-serif}
.drop{display:grid;min-height:240px;place-content:center;justify-items:center;gap:12px;padding:28px;border:1.5px dashed #8a9c8f;border-radius:8px;background:#fffefa;text-align:center;transition:.15s}
.drop.active{border-color:#bf4f34;background:#fff4ef}.mark{display:grid;width:46px;height:46px;place-items:center;border-radius:50%;background:#e1eee2;color:#306347;font:26px 'Trebuchet MS',sans-serif}
.drop strong{font-size:20px;font-weight:500}.drop span{color:#6a746e;font:14px/1.4 'Trebuchet MS',sans-serif}input[type=file]{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0)}
.choose{color:#a33e28!important;text-decoration:underline;text-underline-offset:3px;cursor:pointer}.selection{min-height:22px;margin:14px 0;color:#5d6963;font:13px/1.5 'Trebuchet MS',sans-serif}
.actions{display:flex;align-items:center;gap:14px}button{padding:12px 18px;border:0;border-radius:5px;background:#285b42;color:white;font:700 14px 'Trebuchet MS',sans-serif;cursor:pointer}button:disabled{opacity:.45;cursor:wait}
#status{color:#5d6963;font:13px 'Trebuchet MS',sans-serif}section{margin-top:38px}h2{margin:0 0 12px;font-size:20px;font-weight:500}ul{margin:0;padding:0;list-style:none;border-top:1px solid #d9dfd8}
li{display:flex;justify-content:space-between;gap:16px;padding:12px 2px;border-bottom:1px solid #d9dfd8;font:14px/1.4 'Trebuchet MS',sans-serif;overflow-wrap:anywhere}li small{flex:0 0 auto;color:#6a746e;font-family:monospace}.empty{color:#818b84;font:14px 'Trebuchet MS',sans-serif}
@media(max-width:480px){body{padding:32px 16px}.drop{min-height:210px}.actions{align-items:flex-start;flex-direction:column}}
</style></head><body><main>
<header><p class="eyebrow">Local file inbox</p><h1>Send the files over.</h1><p class="lede">Choose a ZIP or other files. They’ll be saved on this machine for me to inspect.</p></header>
<form id="form"><label class="drop" id="drop" for="files"><span class="mark" aria-hidden="true">+</span><strong>Drop files here</strong><span>or <span class="choose">browse your device</span></span></label>
<input id="files" name="files" type="file" multiple><p class="selection" id="selection">No files selected</p><div class="actions"><button id="submit" type="submit" disabled>Upload files</button><span id="status" role="status" aria-live="polite">Up to 100 MB per upload</span></div></form>
<section><h2>Saved here</h2><ul id="saved"><li class="empty">No files yet</li></ul></section></main>
<script>
const form=document.querySelector('#form'),input=document.querySelector('#files'),drop=document.querySelector('#drop'),submit=document.querySelector('#submit'),status=document.querySelector('#status'),selection=document.querySelector('#selection'),saved=document.querySelector('#saved');
function showSelection(){selection.textContent=input.files.length?[...input.files].map(f=>f.name).join(', '):'No files selected';submit.disabled=!input.files.length}
function size(bytes){return bytes<1048576?`${Math.ceil(bytes/1024)} KB`:`${(bytes/1048576).toFixed(1)} MB`}
async function refresh(){const files=await(await fetch('/files')).json();saved.replaceChildren();if(!files.length){const row=document.createElement('li');row.className='empty';row.textContent='No files yet';saved.append(row);return}for(const file of files){const row=document.createElement('li'),name=document.createElement('span'),bytes=document.createElement('small');name.textContent=file.name;bytes.textContent=size(file.size);row.append(name,bytes);saved.append(row)}}
input.addEventListener('change',showSelection);for(const event of ['dragenter','dragover'])drop.addEventListener(event,e=>{e.preventDefault();drop.classList.add('active')});for(const event of ['dragleave','drop'])drop.addEventListener(event,e=>{e.preventDefault();drop.classList.remove('active')});
drop.addEventListener('drop',e=>{const transfer=new DataTransfer();for(const file of e.dataTransfer.files)transfer.items.add(file);input.files=transfer.files;showSelection()});
form.addEventListener('submit',async e=>{e.preventDefault();submit.disabled=true;status.textContent='Uploading…';try{const response=await fetch('/upload',{method:'POST',body:new FormData(form)}),result=await response.json();if(!response.ok)throw Error(result.error||'Upload failed');status.textContent=`Uploaded ${result.files.length} file${result.files.length===1?'':'s'}`;input.value='';showSelection();await refresh()}catch(error){status.textContent=error.message;submit.disabled=!input.files.length}});
refresh().catch(()=>status.textContent='Could not load saved files');
</script></body></html>"""


class UploadHandler(BaseHTTPRequestHandler):
    def send_json(self, status, data):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            body = PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path == "/files":
            files = [{"name": f.name, "size": f.stat().st_size} for f in sorted(UPLOAD_DIR.iterdir()) if f.is_file()]
            self.send_json(200, files)
        else:
            self.send_json(404, {"error": "Not found"})

    def do_POST(self):
        if urlparse(self.path).path != "/upload":
            self.send_json(404, {"error": "Not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_REQUEST_SIZE:
            self.send_json(413, {"error": "Upload must be between 1 byte and 100 MB"})
            return
        content_type = self.headers.get("Content-Type", "")
        if not content_type.lower().startswith("multipart/form-data;"):
            self.send_json(400, {"error": "Expected a multipart file upload"})
            return
        raw = (f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("ascii") + self.rfile.read(length))
        message = BytesParser(policy=policy.default).parsebytes(raw)
        UPLOAD_DIR.mkdir(exist_ok=True)
        stored = []
        for part in message.iter_parts():
            filename = part.get_filename()
            if not filename:
                continue
            name = Path(filename.replace("\\", "/").replace("\0", "")).name.strip()
            if not name or name in {".", ".."}:
                continue
            destination, suffix = UPLOAD_DIR / name, 1
            while destination.exists():
                destination = UPLOAD_DIR / f"{Path(name).stem}_{suffix}{Path(name).suffix}"
                suffix += 1
            destination.write_bytes(part.get_payload(decode=True) or b"")
            stored.append(destination.name)
        if not stored:
            self.send_json(400, {"error": "No files were included"})
        else:
            self.send_json(200, {"files": stored})

    def log_message(self, format, *args):
        print(f"{self.address_string()} - {format % args}")


if __name__ == "__main__":
    UPLOAD_DIR.mkdir(exist_ok=True)
    server = ThreadingHTTPServer((HOST, PORT), UploadHandler)
    print(f"File inbox running at http://{HOST}:{PORT}")
    print(f"Uploaded files are saved in {UPLOAD_DIR}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopping file inbox")
        server.server_close()