import yt_dlp
import os

# 윈도우의 Downloads 폴더 경로 가져오기
downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads")

# 필수 입력: 사용자로부터 검색어 입력 받기
query = input("검색어를 입력하세요 (필수): ").strip()
while not query:
    query = input("검색어는 필수입니다. 검색어를 입력하세요: ").strip()

# 필수 입력: 사용자로부터 다운로드할 동영상 개수 입력 받기
while True:
    max_videos_input = input("다운로드할 동영상 개수를 입력하세요 (필수): ").strip()
    if max_videos_input.isdigit():
        max_videos = int(max_videos_input)
        break
    else:
        print("유효한 정수를 입력해 주세요.")

search_url = f"ytsearch{max_videos}:{query}"

# 다운로드 옵션 (파일명 템플릿 등)
ydl_opts = {
    "outtmpl": os.path.join(downloads_dir, "%(title)s.%(ext)s"),
}

with yt_dlp.YoutubeDL(ydl_opts) as ydl:
    ydl.download([search_url])
