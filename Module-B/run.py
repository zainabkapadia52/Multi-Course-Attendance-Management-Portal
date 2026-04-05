from app import create_app
import os

os.chdir(os.path.dirname(os.path.abspath(__file__)))

app = create_app()

if __name__ == "__main__":
    # Enable threaded mode for concurrent request handling
    # threaded=True: Each request runs in its own thread for true parallelism
    app.run(debug=True, port=5050, threaded=True)