import os
import time
import subprocess
import datetime
import re
import traceback
import locale

from flask import Flask, request, render_template_string, Response, send_from_directory
from youtubesearchpython import VideosSearch

app = Flask(__name__)

# Windows 다운로드 폴더 경로
DOWNLOAD_FOLDER = os.path.join(os.path.expanduser("~"), "Downloads")
# encoding = locale.getpreferredencoding(False)

######################
# secure_filename 대체
######################
def custom_secure_filename(filename):
    # 공백은 언더스코어로 변환
    filename = "_".join(filename.split())
    # 알파벳, 숫자, 한글, 밑줄, 하이픈, 점(.) 만 허용
    filename = re.sub(r"[^a-zA-Z0-9가-힣_.-]", "", filename)
    return filename


######################
# yt-dlp 다운로드 함수
######################
def download_video_with_ytdlp(video_url, output_path):
    """
    1) --get-filename 으로 실제 다운로드될 파일 경로(final_path) 확인
    2) 실제 다운로드 진행
    3) 다운로드 완료 후 파일명을 custom_secure_filename()으로 변경
    4) 파일 수정/접근 시간(mtime, atime)을 현재 시각으로 설정 (os.utime)
    """
    # 1) 파일 경로 확인
    cmd_get_filename = [
        'yt-dlp',
        '--paths', output_path,
        '--get-filename',
        '-o', '%(title)s.%(ext)s',
        video_url
    ]

    r_filename = subprocess.run(cmd_get_filename, capture_output=True, text=True)
    print(f"r_filename: {r_filename}")
    if r_filename.returncode != 0:
        raise Exception(f"Failed to get filename: {r_filename.stderr.strip()}")

    final_path = r_filename.stdout.strip()

    # 2) 실제 다운로드
    cmd_download = [
        'yt-dlp',
        '--paths', output_path,
        '-o', final_path,
        video_url
    ]
    
    r_download = subprocess.run(cmd_download, capture_output=True, text=True)
    if r_download.returncode != 0:
        raise Exception(f"Download error: {r_download.stderr.strip()}")

    # 3) 파일명 변경
    #    다운로드가 끝나면, 실제로 생성된 파일(final_path)을 custom_secure_filename으로 바꿔줍니다.
    base_dir = os.path.dirname(final_path)
    original_name = os.path.basename(final_path)
    new_name = original_name
    # new_name = custom_secure_filename(original_name)
    new_path = os.path.join(base_dir, new_name)

    print(f"new_path: {new_path}")
    # 같은 이름이면 변경 불필요
    if new_path != final_path:
        os.rename(final_path, new_path)

    # 4) 수정/접근 시간 현재 시각으로 맞춤 (Windows 탐색기에서 '수정된 날짜'가 최신으로 표시)
    print("4) 수정/접근 시간 현재 시각으로 맞춤\n\n")
    current_time = time.time()
    os.utime(new_path, (current_time, current_time))

    return new_path  # 새 경로 반환


##########################
# 메인 페이지 (GET /)
##########################
@app.route("/")
def index():
    """
    단순 HTML 페이지:
    - 키워드, 다운로드 개수 입력
    - SSE로 진행 상황(메시지) 수신
    """
    html = """
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <title>유튜브 다운 v0.3</title>
        <style>
            * {
                margin: 0; padding: 0;
                box-sizing: border-box;
                font-family: 'Segoe UI', sans-serif;
            }
            body {
                background: #f3f4f6;
                display: flex; flex-direction: column;
                align-items: center; min-height: 100vh;
                padding: 2rem;
            }
            .container {
                background: #fff;
                border-radius: 8px;
                box-shadow: 0 8px 16px rgba(0,0,0,0.1);
                max-width: 500px;
                width: 100%;
                padding: 2rem;
            }
            h1 {
                margin-bottom: 1.5rem; color: #333;
            }
            label {
                margin-top: 0.5rem; margin-bottom: 0.2rem;
                font-weight: bold; color: #555;
            }
            input[type="text"], input[type="number"] {
                padding: 0.5rem; margin-bottom: 1rem;
                border: 1px solid #ccc; border-radius: 4px;
                width: 100%;
            }
            button {
                background: #6366f1; color: #fff; border: none;
                padding: 0.8rem; border-radius: 4px; cursor: pointer;
                font-size: 1rem;
            }
            button:hover {
                background: #4f46e5;
            }
            #messages {
                margin-top: 1rem; background: #f9fafb;
                border-radius: 4px; padding: 1rem;
                min-height: 100px;
            }
            .msg {
                margin-bottom: 0.5rem;
            }
            a {
                color: #2563eb;
                text-decoration: underline;
                margin-left: 8px;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>유튜브 다운 v0.3 by pro9dan</h1>
            <label for="keyword">유튜브 검색 키워드</label>
            <input type="text" id="keyword" placeholder="예: 파이썬 튜토리얼">

            <label for="count">다운로드 개수</label>
            <input type="number" id="count" min="1" max="50" value="1">

            <button onclick="startDownload()">다운로드하기</button>

            <div id="messages"></div>
        </div>

        <script>
            function startDownload() {
                // 입력값 가져오기
                const keyword = document.getElementById('keyword').value.trim();
                const count = document.getElementById('count').value.trim();

                if (!keyword) {
                    alert('검색 키워드를 입력해 주세요.');
                    return;
                }

                // 기존 메시지 지우기
                const msgBox = document.getElementById('messages');
                msgBox.innerHTML = '';

                // SSE 연결
                const url = `/download?keyword=${encodeURIComponent(keyword)}&count=${encodeURIComponent(count)}`;
                const evtSource = new EventSource(url);

                // 서버에서 온 메시지를 화면에 표시
                evtSource.onmessage = function(event) {
                    const div = document.createElement('div');
                    div.className = 'msg';
                    div.innerHTML = event.data; // a 태그 파싱 위해 innerHTML
                    msgBox.appendChild(div);
                };

                // 에러 처리 (네트워크 단절 등)
                evtSource.onerror = function(err) {
                    const div = document.createElement('div');
                    div.className = 'msg';
                    div.textContent = '에러 발생 혹은 연결이 종료되었습니다.';
                    msgBox.appendChild(div);
                    evtSource.close();
                };
            }
        </script>
    </body>
    </html>
    """
    return render_template_string(html)


##########################
# SSE 다운로드 라우트
##########################
from urllib.parse import quote, unquote

@app.route("/download")
def sse_download():
    """
    /download?keyword=...&count=...
    - SSE(Server-Sent Events)로 진행 메시지 전송
    - 각 파일 다운로드 후 링크를 포함한 메시지 전달
    """
    keyword = request.args.get("keyword", "").strip()
    count = request.args.get("count", "1").strip()

    def generate():
        if not keyword:
            yield f"data: 검색 키워드를 입력해 주세요.\n\n"
            return

        try:
            n = int(count)
        except ValueError:
            n = 1

        yield f"data: 다운로드를 시작합니다.\n\n"

        try:
            videos_search = VideosSearch(keyword, limit=n)
            results = videos_search.result().get('result', [])

            if not results:
                yield f"data: 검색 결과가 없습니다.\n\n"
                yield f"data: 다운로드가 모두 끝났습니다.\n\n"
                return
            else:
                for idx, item in enumerate(results, start=1):
                    video_id = item['id']
                    video_url = f'https://www.youtube.com/watch?v={video_id}'
                    print(f"video_url: {video_url}")
                    try:
                        saved_path = download_video_with_ytdlp(video_url, DOWNLOAD_FOLDER)
                        print(f"saved_path: {saved_path}")

                        # 링크용 파일명 (파일명만 따서 URL-encode)
                        filename_only = os.path.basename(saved_path)
                        # safe_name = custom_secure_filename(filename_only)  # 디렉토리 탈출/위험 문자 방지
                        safe_name = filename_only  # 디렉토리 탈출/위험 문자 방지
                        # encoded_name = quote(safe_name)
                        encoded_name = safe_name

                        # 메시지에 링크(a태그) 포함
                        download_link = f'<a href="/downloadfile?filename={encoded_name}" download>다운로드</a>'

                        yield f"data: {idx}번째 다운로드 완료! ({saved_path}) {download_link}\n\n"
                    except Exception as e:
                        yield f"data: {idx}번째 영상 오류: {str(e)}\n\n"
                        print(traceback.format_exc(), flush=True)
                yield f"data: 다운로드가 모두 끝났습니다.\n\n"

        except Exception as e:
            yield f"data: 오류가 발생했습니다: {str(e)}\n\n"
            print(traceback.format_exc(), flush=True)

    return Response(generate(), mimetype="text/event-stream")


##########################
# 파일 서빙 라우트
##########################
@app.route("/downloadfile")
def downloadfile():
    """
    /downloadfile?filename=...
    - DOWNLOAD_FOLDER 내 해당 파일을 브라우저로 전송 (as_attachment=True)
    """
    filename = request.args.get("filename", "")
    # URL 디코딩
    filename = unquote(filename)
    print(f"downloadfile() filename: {filename}")
    # 보안상 안전한 파일명으로 변환 (디렉토리 탈출 등 방지)
    # safe_name = custom_secure_filename(filename)
    safe_name = filename

    # 실제로 DOWNLOAD_FOLDER 안에 safe_name 파일이 있어야만 성공
    if not safe_name:
        return "Invalid filename", 400

    file_path = os.path.join(DOWNLOAD_FOLDER, safe_name)
    if not os.path.exists(file_path):
        return f"파일이 존재하지 않습니다: {safe_name}", 404

    # as_attachment=True → 브라우저가 '파일로 다운'하도록 지시
    return send_from_directory(DOWNLOAD_FOLDER, safe_name, as_attachment=True)


if __name__ == "__main__":
    app.run(debug=True)
