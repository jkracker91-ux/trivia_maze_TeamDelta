FROM python:3.11-slim

# Prevent interactive prompts during package installation
ARG DEBIAN_FRONTEND=noninteractive

# Install git so we can clone the repo
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

# Clone your repository
RUN git clone https://github.com/citronoiseau/S504_TriviaMaze_TeamDelta.git /app

# Set the working directory
WORKDIR /app

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Run the maze (CLI entrypoint is main.py; maze.py is domain logic only)
CMD ["python", "main.py"]
