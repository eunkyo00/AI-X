"""Parse the browser's existing multipart upload contract without extra libraries."""
from email import policy
from email.parser import BytesParser
import json

MAX_REQUEST = 102 * 1024 * 1024


def parse_files(content_type, data):
    if not content_type.startswith('multipart/form-data;'):
        raise ValueError('파일 등록에는 multipart/form-data 요청이 필요합니다.')
    message = BytesParser(policy=policy.default).parsebytes(
        f'Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n'.encode()+data)
    if not message.is_multipart() or message.defects:
        raise ValueError('파일 전송 형식이 올바르지 않습니다.')
    files, paths, relative = [], None, None
    for part in message.iter_parts():
        name = part.get_param('name', header='content-disposition')
        payload = part.get_payload(decode=True)
        if payload is None:
            raise ValueError('올바르지 않은 파일 전송 내용입니다.')
        if name in {'file', 'files'}:
            files.append((part.get_filename() or '', payload))
        elif name == 'paths':
            paths = json.loads(payload.decode('utf-8'))
        elif name == 'relative_path':
            relative = payload.decode('utf-8')
    if paths is not None:
        if not isinstance(paths, list) or len(paths) != len(files) or not all(isinstance(p, str) for p in paths):
            raise ValueError('파일과 상대 경로 수가 일치하지 않습니다.')
        files = [(path, item[1]) for path, item in zip(paths, files)]
    elif relative is not None:
        if len(files) != 1:
            raise ValueError('단일 파일 경로가 필요합니다.')
        files = [(relative, files[0][1])]
    return files
