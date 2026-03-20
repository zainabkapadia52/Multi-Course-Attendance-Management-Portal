from app import create_app
import os

os.chdir(os.path.dirname(os.path.abspath(__file__)))

app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port=5000)