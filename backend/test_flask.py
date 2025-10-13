from flask import Flask

app = Flask(__name__)

@app.route('/')
def home():
    return "Hello from Flask!"

if __name__ == '__main__':
    print("Starting test server on http://127.0.0.1:5001")
    app.run(host='0.0.0.0', port=5001, debug=False, threaded=True)
