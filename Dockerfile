# Private research API only. GitHub Pages hosts the public static preview.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FACILITY_RISK_REQUIRE_AUTH=1 \
    FACILITY_RISK_DB=/app/data/facility_risk.sqlite
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --uid 10001 --create-home --shell /usr/sbin/nologin facility
COPY facilityrisk ./facilityrisk
COPY web ./web
EXPOSE 8765
USER 10001:10001
# The CLI explicitly refuses non-loopback binding without a long auth secret.
CMD ["python","-m","facilityrisk","serve","--host","0.0.0.0","--port","8765"]
