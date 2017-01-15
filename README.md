# Canvas Presentation Transcript

This is a script to download transcripts from Canvas presentations.

Canvas presentations usually have transcripts, but you cannot just copy-paste them.

This script attempts to download transcripts via associated xml documents. 


This script works specifically for USF, but you can modify the `canvasUrl` 
and login functions to suit your needs.


I wrote this a long time ago when I was even worse at Python, I'd like to fix this 
up, but it's not worth it as it works.

## How to use

**Setup**

- `virtualenv venv`
- `pip install -r requirements.txt`

**Running**

- `python go.py`


## License

Do whatever you want. No attribution required. No warranty. 