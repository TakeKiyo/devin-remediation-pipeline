FROM python:3.12-slim

# The orchestrator only moves metadata over HTTPS: no git, no node, no
# application dependencies. All code work happens inside the Devin session.
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY orchestrator/ ./orchestrator/
COPY fixtures/ ./fixtures/

ENV PYTHONUNBUFFERED=1
CMD ["python", "-m", "orchestrator.main"]
