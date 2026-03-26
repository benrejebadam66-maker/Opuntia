# Opuntia

Opuntia is a developer-focused AI assistant platform with local tooling, agent workflows, and a modern desktop experience.

## For New Contributors (Windows)

1. Clone the repository:
   ```powershell
   git clone https://github.com/benrejebadam66-maker/Opuntia.git
   cd Opuntia
   ```

2. Create and activate Python virtual environment:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

3. Install Python dependencies:
   ```powershell
   pip install -r requirements.txt
   ```

4. Run the backend app:
   ```powershell
   python .\version0.2.py
   ```

5. Optional: run frontend in a second terminal:
   ```powershell
   cd .\glass-ui
   npm install
   npm run dev
   ```

## Start Scripts

Use these shortcuts from the project root:

- Backend:
  ```powershell
  .\scripts\start_backend.ps1
  ```
- Frontend:
  ```powershell
  .\scripts\start_frontend.ps1
  ```

## Testing

Run backend tests:

```powershell
pytest
```

## Contributing

1. Create a branch:
   ```powershell
   git checkout -b feature/your-change
   ```
2. Commit and push:
   ```powershell
   git add .
   git commit -m "Describe your change"
   git push -u origin feature/your-change
   ```
3. Open a Pull Request on GitHub.
