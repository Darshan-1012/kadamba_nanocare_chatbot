"""Nanocare Wellness Report Engine — Entry point.
Run from project root: python run.py
"""
# pyrefly: ignore [missing-import]
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="localhost",
        port=8001,
        reload=True,
        reload_dirs=["app"],
        reload_excludes=["reports/*", "*.pdf", "*.json", "cache/*"],
    )
