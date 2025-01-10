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
STOCK_SIZE = 100
REPLENISH_THRESHOLD = 20
INITIAL_STOCK = 10
REPLENISH_CHUNK_SIZE = 5
STOCK_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dh_params_stock.json")

# Shared storage for DH parameters
dh_params_stock = Queue(maxsize=STOCK_SIZE)
replenishment_active = False
lock = threading.Lock()

_initialization_done = False  # Prevent repeated initialization


def generate_dh_param():
    """Generate a Diffie-Hellman parameter in PEM format."""
    parameters = dh.generate_parameters(generator=2, key_size=2048)
    pem = parameters.parameter_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.ParameterFormat.PKCS3
    )
    return pem.decode('utf-8')

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

        with open(STOCK_FILE, "w+") as f:
            for param in params_list:
                json.dump(param, f)
                f.write("\n")
        print(f"[Storage] Saved {len(params_list)} parameters to {STOCK_FILE}")


def load_stock():
    """Load the stock from a JSON file."""
    try:
        if os.path.exists(STOCK_FILE):
            with open(STOCK_FILE, "r") as f:
                params = [json.loads(line) for line in f if line.strip()]
                for param in params[:STOCK_SIZE]:
                    dh_params_stock.put(param)
            print(f"[Storage] Loaded {dh_params_stock.qsize()} parameters from {STOCK_FILE}")
        else:
            print(f"[Storage] {STOCK_FILE} does not exist. Starting with empty stock.")
    except Exception as e:
        print(f"[Storage] Error loading stock: {e}")

def replenishment_thread():
    """Background thread to replenish DH parameter stock."""
    global replenishment_active
    while True:
        try:
            if not replenishment_active and dh_params_stock.qsize() < REPLENISH_THRESHOLD:
                print("[Replenishment] Stock fell below threshold. Starting replenishment.")
                replenishment_active = True

            if replenishment_active:
                missing_count = STOCK_SIZE - dh_params_stock.qsize()
                chunk_size = min(REPLENISH_CHUNK_SIZE, missing_count)

                if chunk_size > 0:
                    print(f"[Replenishment] Generating {chunk_size} DH parameters...")

                with ThreadPoolExecutor() as executor:
                    new_params = list(executor.map(lambda _: generate_dh_param(), range(chunk_size)))

                for param in new_params:
                    dh_params_stock.put(param)

                save_stock()

                print(f"[Replenishment] Stock replenished. Current stock: {dh_params_stock.qsize()}")

                if dh_params_stock.qsize() >= STOCK_SIZE:
                    print("[Replenishment] Stock is full. Stopping replenishment.")
                    replenishment_active = False
        except Exception as e:
            print(f"[Replenishment] Error: {e}")
        time.sleep(1)


@app.route('/params', methods=['GET'])
def get_dh_param():
    """API endpoint to serve a DH parameter."""
    try:
        dh_param = dh_params_stock.get_nowait()
        print(f"[Flask] Served DH parameter. Remaining stock: {dh_params_stock.qsize()}")
        return Response(dh_param, mimetype='text/plain')
    except Exception:
        print("[Flask] Stock is empty. Returning 503.")
        return Response("Stock is empty, please retry shortly.", mimetype='text/plain', status=503)


def init_application():
    """Initialize the application with stock and background threads."""
    # Load existing stock from file
    print("[Main] Loading stock from file...")
    load_stock()

    # Generate initial stock only if needed
    if dh_params_stock.empty():
        print("[Main] Generating initial stock...")
        for _ in range(INITIAL_STOCK):
            dh_params_stock.put(generate_dh_param())
        save_stock()

    print(f"[Main] Stock ready with {dh_params_stock.qsize()} DH parameters.")

    # Start the replenishment thread
    replenishment_worker = threading.Thread(target=replenishment_thread, daemon=True, name="ReplenishmentThread")
    replenishment_worker.start()

    # Start the Flask server thread
    flask_worker = threading.Thread(target=flask_thread, daemon=True, name="FlaskThread")
    flask_worker.start()

    # Keep the main thread alive to monitor the application
    while True:
        time.sleep(1)
