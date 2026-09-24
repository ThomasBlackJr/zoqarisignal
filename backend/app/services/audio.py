from pathlib import Path

from fastapi import HTTPException, UploadFile
from mutagen import File as AudioFile

MIME = {".wav": "audio/wav", ".mp3": "audio/mpeg", ".m4a": "audio/mp4"}


def inspect_audio(path: Path) -> float:
    header = path.read_bytes()[:16] if path.stat().st_size < 16 else None
    if header is None:
        with path.open("rb") as stream:
            header = stream.read(16)
    suffix = path.suffix.lower()
    valid = (
        (suffix == ".wav" and header[:4] == b"RIFF" and header[8:12] == b"WAVE")
        or (
            suffix == ".mp3"
            and (header[:3] == b"ID3" or (len(header) >= 2 and header[0] == 255 and header[1] & 224 == 224))
        )
        or (suffix == ".m4a" and header[4:8] == b"ftyp")
    )
    if not valid:
        raise HTTPException(422, "The file content does not match a supported audio format")
    try:
        audio = AudioFile(path)
        duration = float(audio.info.length) if audio is not None else 0
        if duration <= 0:
            raise ValueError("Empty audio")
        return duration
    except Exception as exc:
        raise HTTPException(422, "The audio file is damaged or contains no playable audio") from exc


async def save_upload(upload: UploadFile, path: Path, limit: int) -> tuple[int, float]:
    size = 0
    try:
        with path.open("xb") as stream:
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                if size > limit:
                    raise HTTPException(413, "Recording exceeds the configured upload size limit")
                stream.write(chunk)
        return size, inspect_audio(path)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()
