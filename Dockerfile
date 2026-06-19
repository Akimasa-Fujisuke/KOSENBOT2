FROM python:3.11-slim

# 作業ディレクトリの作成
WORKDIR /app

# 依存関係ファイルをコピーしてインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 残りのソースコードをコピー
COPY . .

# 権限を変更するなら /app に対して行います（通常は無くても動きますが、念のため）
RUN chmod -R 755 /app

# ボットを実行（2.py を実行）
CMD ["python", "2.py"]