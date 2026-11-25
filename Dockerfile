FROM python:3.13-slim
# LightGBM needs the OpenMP runtime
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
RUN useradd -m -u 1000 user
WORKDIR /home/user/app
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=user . .
USER user
ENV CREASE_PUBLIC=1 CREASE_HOST=0.0.0.0 CREASE_PUBLIC_IMAGES=1 PYTHONUNBUFFERED=1
EXPOSE 10000
CMD ["python", "main.py", "serve"]
