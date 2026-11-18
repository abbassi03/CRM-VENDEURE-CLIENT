# CRM VENDEURE-CLIENT

A responsive business CRM built with Python, Flask, SQLite, HTML, CSS and Bootstrap. It includes customer and supplier management, inventory, sales, purchases, invoices, bank accounts, bank transactions, expenses, employees and payroll.

## Features

- Secure login with hashed passwords
- Dashboard with sales, expenses, cash movement, customers, employees, stock alerts and unpaid invoice indicators
- CRUD (create, read, update, delete) for 12 business modules
- Search across records in each module
- CSV export for every module
- Demo dataset and one-click demo data restoration
- Change-password page
- Responsive layout for desktop, tablet and mobile
- SQLite database created automatically on first launch

## Requirements

- Python 3.10+
- pip

## Run on Kali Linux / Debian / Ubuntu

```bash
cd crm-vendeure-client
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python app.py
```

Open: http://127.0.0.1:5000

If your Linux installation needs the venv package first:

```bash
sudo apt update
sudo apt install python3-venv python3-pip
```

## Demo login

- Username: `admin`
- Password: `Admin@123`

Change the demo password immediately from **Settings**.

## Database

The app creates `crm.db` in the project folder. To use another location, set `CRM_DATABASE` before starting the app:

```bash
export CRM_DATABASE="$HOME/crm-vendeure-client.db"
python app.py
```

## Configuration before deployment

Set a long, random secret key and run behind a production WSGI server with HTTPS:

```bash
export SECRET_KEY="replace-with-a-long-random-secret"
```

Do not expose Flask's development server directly to the public internet. Back up `crm.db` regularly. Bootstrap and Bootstrap Icons are loaded from jsDelivr, and fonts from Google Fonts, so the default design uses an internet connection for those assets.

## Important scope notes

This is a functional CRM starter application with persistent records and demo data. It is not yet an accounting-certified or payroll-compliance product. Bank transactions, sales, invoices, purchases, inventory quantities and payroll records are currently entered as business records; automatic accounting reconciliation, tax filing, invoice PDF generation, payment-gateway integration, multi-user roles and audit logging would be the next production-hardening phase. Use test data until your workflows and local legal/accounting requirements have been validated.

## Project structure

```text
crm-vendeure-client/
├── app.py
├── requirements.txt
├── README.md
├── templates/
│   ├── base.html
│   ├── login.html
│   ├── dashboard.html
│   ├── list.html
│   ├── form.html
│   └── settings.html
└── static/
    ├── css/style.css
    └── js/app.js
```
