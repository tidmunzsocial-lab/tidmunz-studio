"""SnapGen WEB: browser-only image generation through the existing extension."""
from pathlib import Path
from threading import RLock
import base64,hashlib,io,json,os
from PIL import Image, ImageOps
import snapgen_chrome_relay

_lock=RLock()

def generate(prompt, refs, output_dir, name, aspect):
    if aspect!="16:9":raise RuntimeError("SnapGen Web รองรับ 16:9 เท่านั้น")
    if len(refs)>5:raise RuntimeError("SnapGen Web มี Ref เกิน 5 รูป — หยุดไม่ลดเรฟเอง")
    pass  # The Chrome extension validates live Web price and credits before sending
    files=[]; fingerprints=[]
    for x in refs:
        p=Path(x)
        if not p.is_file():raise RuntimeError("Ref missing: "+p.name)
        raw=p.read_bytes()
        # Prepare refs locally; web generation checks credits before the paid click.
        with Image.open(io.BytesIO(raw)) as source:
            converted = ImageOps.exif_transpose(source).convert("RGB")
            converted.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
            stream = io.BytesIO()
            converted.save(stream, "JPEG", quality=91, optimize=True)
            raw = stream.getvalue()
        mime = "image/jpeg"
        files.append("data:"+mime+";base64,"+base64.b64encode(raw).decode("ascii"))
        fingerprints.append(hashlib.sha256(raw).hexdigest())
    folder=Path(output_dir);folder.mkdir(parents=True,exist_ok=True)
    signature=hashlib.sha256(json.dumps([prompt,aspect,fingerprints],ensure_ascii=False).encode("utf8")).hexdigest()[:18]
    receipt=folder/f".{name}_snapgen_web_{signature}.json"
    with _lock:
        if receipt.is_file():
            try:old=json.loads(receipt.read_text("utf8"))
            except (ValueError,OSError):old={}
            saved=Path(old.get("output") or "")
            if old.get("state")=="completed" and saved.is_file():return str(saved)
            raise RuntimeError(f"{name}: SnapGen Web อาจรับงานไปแล้ว — ตรวจ History ห้ามยิงซ้ำ")
        receipt.write_text(json.dumps({"state":"dispatching","model":"grok-image",
                                       "price_limit":3.0}),encoding="utf8")
        try:
            result=snapgen_chrome_relay.RELAY.run({
                "type":"snapgen_web_image","prompt":prompt,"images":files,
                "model":"grok-image","aspect_ratio":"16:9","price_ceiling":3.0})
        except Exception as e:
            receipt.write_text(json.dumps({"state":"dispatch_unknown",
                            "error":str(e)[:120]}),encoding="utf8")
            raise RuntimeError("SnapGen Web: ไม่ได้สถานะแน่ชัด ตรวจ History ก่อน") from e
        if result.get("error"):
            if result.get("send_state")=="not_sent":receipt.unlink(missing_ok=True)
            else:receipt.write_text(json.dumps({"state":"possibly_sent","error":
                       str(result["error"])[:180]}),encoding="utf8")
            raise RuntimeError(str(result["error"])[:500])
        photos=result.get("images") or []
        if len(photos)!=1 or not str(photos[0]).startswith("data:image/"):
            receipt.write_text(json.dumps({"state":"result_unknown"}),encoding="utf8")
            raise RuntimeError("SnapGen Web: ผลลัพธ์ไม่ชัดเจน — ห้ามส่งซ้ำ")
        try:
            raw=base64.b64decode(str(photos[0]).split(",",1)[1],validate=True)
            with Image.open(io.BytesIO(raw)) as im:
                if im.width<600 or im.height<300 or abs(im.width/im.height-16/9)>.2:
                    raise ValueError("image dimensions invalid")
                output=folder/(name+"_snapgen_web.png")
                temp=output.with_suffix(".partial.png")
                im.save(temp,"PNG");os.replace(temp,output)
        except Exception as e:
            receipt.write_text(json.dumps({"state":"result_unreadable"}),encoding="utf8")
            raise RuntimeError("SnapGen Web: เก็บภาพไม่สำเร็จ ห้ามส่งซ้ำ") from e
        receipt.write_text(json.dumps({"state":"completed","output":str(output),
                        "credits":result.get("web_price")}),encoding="utf8")
        return str(output)
