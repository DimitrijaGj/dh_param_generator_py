#!/usr/bin/env python3

import threading
import time
import json
from flask import Flask, Response
from cryptography.hazmat.primitives.asymmetric import dh
from cryptography.hazmat.primitives import serialization
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
import os

app = Flask(__name__)

# Configuration parameters for stock management
STOCK_SIZE = 100  # Maximum size of DH parameters stock
REPLENISH_THRESHOLD = 20  # Threshold below which replenishment starts
INITIAL_STOCK = 10  # Initial number of DH parameters to generate
REPLENISH_CHUNK_SIZE = 5  # Number of parameters to generate per replenishment cycle
STOCK_FILE = "/Users/dgjoshev/development/gitlab_reuter365_net/devops/tools/dhparam_gen_python/dh_params_stock.json"  # Added stock file path

# Shared storage for DH parameters
# Using a thread-safe queue with a fixed maximum size
dh_params_stock = Queue(maxsize=STOCK_SIZE)
replenishment_active = False  # Flag to indicate if replenishment is active
lock = threading.Lock()  # Lock for thread-safe operations (if needed)

# Function to generate a new DH parameter in PEM format
def generate_dh_param():
    # Generate Diffie-Hellman parameters with a 2048-bit key size
    parameters = dh.generate_parameters(generator=2, key_size=2048)
    # Serialize the parameters to PEM format
    pem = parameters.parameter_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.ParameterFormat.PKCS3
    )
    return pem.decode('utf-8')  # Return as a decoded string

def save_stock():
    """Save the current stock to a JSON file"""
    with lock:
        # Convert queue to list for saving
        params_list = []
        temp_queue = Queue()
        while not dh_params_stock.empty():
            param = dh_params_stock.get()
            params_list.append(param)
            temp_queue.put(param)

        # Restore the queue
        while not temp_queue.empty():
            dh_params_stock.put(temp_queue.get())

        with open(STOCK_FILE, "w") as f:
            for param in params_list:
                json.dump(param, f)
                f.write("\n")
        print(f"[Storage] Saved {len(params_list)} parameters to {STOCK_FILE}")

def load_stock():
    """Load the stock from JSON file"""
    try:
        with open(STOCK_FILE, "r") as f:
            params = [json.loads(line) for line in f if line.strip()]
            for param in params[:STOCK_SIZE]:  # Respect STOCK_SIZE limit
                dh_params_stock.put(param)
        print(f"[Storage] Loaded {dh_params_stock.qsize()} parameters from {STOCK_FILE}")
    except FileNotFoundError:
        print(f"[Storage] {STOCK_FILE} not found. Starting with empty stock.")

# Function to handle replenishment of the stock in a separate thread
def replenishment_thread():
    global replenishment_active
    while True:
        try:
            # Check if stock level is below the replenishment threshold
            if not replenishment_active and dh_params_stock.qsize() < REPLENISH_THRESHOLD:
                print("[Replenishment] Stock fell below threshold. Starting replenishment.")
                replenishment_active = True

            if replenishment_active:
                # Calculate the number of parameters to generate
                missing_count = STOCK_SIZE - dh_params_stock.qsize()
                chunk_size = min(REPLENISH_CHUNK_SIZE, missing_count)

                if chunk_size > 0:
                    print(f"[Replenishment] Generating {chunk_size} DH parameters...")

                # Generate DH parameters in parallel using a thread pool
                with ThreadPoolExecutor() as executor:
                    new_params = list(executor.map(lambda _: generate_dh_param(), range(chunk_size)))

                # Add generated parameters to the stock
                for param in new_params:
                    dh_params_stock.put(param)

                # Save the updated stock
                save_stock()

                print(f"[Replenishment] Stock replenished. Current stock: {dh_params_stock.qsize()}")

                # Stop replenishment if the stock is full
                if dh_params_stock.qsize() >= STOCK_SIZE:
                    print("[Replenishment] Stock is full. Stopping replenishment.")
                    replenishment_active = False
        except Exception as e:
            print(f"[Replenishment] Error: {e}")  # Log any errors that occur
        time.sleep(1)  # Pause before the next replenishment cycle

# API endpoint to serve a DH parameter
@app.route('/params', methods=['GET'])
def get_dh_param():
    try:
        # Retrieve and remove a DH parameter from the stock
        dh_param = dh_params_stock.get_nowait()
        print(f"[Flask] Served DH parameter. Remaining stock: {dh_params_stock.qsize()}")
        return Response(dh_param, mimetype='text/plain')
    except Exception:
        print("[Flask] Stock is empty. Returning 503.")
        # Return a 503 status if the stock is empty
        return Response("Stock is empty, please retry shortly.", mimetype='text/plain', status=503)

# Function to run the Flask server in a separate thread
def flask_thread():
    print("[Flask] Starting Flask server...")
    try:
        os.nice(-5)  # Attempt to set high priority for this thread (may require permissions)
    except Exception as e:
        print(f"[Flask] Failed to set high priority: {e}")
    # Run the Flask application on port 5002
    app.run(host='0.0.0.0', port=5005, debug=False, use_reloader=False)

def init_application():
    """Initialize the application, stock, and background threads"""
    global replenishment_worker

    # Load existing stock from file
    print("[Init] Loading stock from file...")
    load_stock()

    # Generate initial stock only if needed
    if dh_params_stock.empty():
        print("[Init] Generating initial stock...")
        for _ in range(INITIAL_STOCK):
            dh_params_stock.put(generate_dh_param())
        save_stock()

    print(f"[Init] Stock ready with {dh_params_stock.qsize()} DH parameters.")

    # Start the replenishment thread if not already running
    if not replenishment_worker or not replenishment_worker.is_alive():
        replenishment_worker = threading.Thread(target=replenishment_thread, daemon=True, name="ReplenishmentThread")
        replenishment_worker.start()

# Global variable to track the replenishment thread
replenishment_worker = None

if __name__ == '__main__':
    init_application()
    flask_thread()
