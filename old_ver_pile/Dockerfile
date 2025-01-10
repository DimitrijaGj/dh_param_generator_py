# Use a lightweight Python base image
FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Copy the script and requirements
COPY . /app

#  Install dependencies
RUN pip install --no-cache-dir -r requierments.txt

# Expose the port used by the Flask app
EXPOSE 5005

# Command to run the script
CMD ["sudo", "python3", "dragon_a1.py"]
