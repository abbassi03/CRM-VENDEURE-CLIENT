from __future__ import annotations
import os, sqlite3, secrets, csv, io
from datetime import datetime, date
from functools import wraps
from pathlib import Path
from flask import Flask, g, render_template, request, redirect, url_for, flash, session, abort, Response
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get('CRM_DATABASE', BASE_DIR / 'crm.db'))
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'change-this-secret-key-before-production-' + secrets.token_hex(8))
app.config['MAX_CONTENT_LENGTH'] = 4 * 1024 * 1024

# Each module is backed by a real SQLite table. Fields marked required are validated server-side.
MODULES = {
 'companies': {'title':'Companies','singular':'Company','icon':'bi-buildings','desc':'Manage your legal entities and business details.','fields':[
  ('name','Company name','text',1),('industry','Industry','text',0),('tax_id','Tax / ICE number','text',0),('email','Email','email',0),('phone','Phone','text',0),('address','Address','textarea',0),('city','City','text',0),('website','Website','url',0)]},
 'customers': {'title':'Customers','singular':'Customer','icon':'bi-people','desc':'Centralize customer contacts, history and account details.','fields':[
  ('name','Full name / Company','text',1),('company','Company','text',0),('email','Email','email',0),('phone','Phone','text',0),('tax_id','ICE / Tax ID','text',0),('address','Address','textarea',0),('city','City','text',0),('status','Status','select:Lead,Prospect,Active,Inactive',0),('notes','Notes','textarea',0)]},
 'suppliers': {'title':'Suppliers','singular':'Supplier','icon':'bi-truck','desc':'Keep supplier contacts and payment terms organized.','fields':[
  ('name','Supplier name','text',1),('contact_name','Contact person','text',0),('email','Email','email',0),('phone','Phone','text',0),('tax_id','ICE / Tax ID','text',0),('address','Address','textarea',0),('city','City','text',0),('payment_terms','Payment terms','text',0),('notes','Notes','textarea',0)]},
 'employees': {'title':'Employees','singular':'Employee','icon':'bi-person-badge','desc':'Manage employee records, roles and compensation.','fields':[
  ('name','Full name','text',1),('job_title','Job title','text',0),('department','Department','text',0),('email','Email','email',0),('phone','Phone','text',0),('hire_date','Hire date','date',0),('salary','Monthly salary (MAD)','number',0),('status','Status','select:Active,On leave,Inactive',0)]},
 'products': {'title':'Products & Services','singular':'Product','icon':'bi-box-seam','desc':'Track SKUs, prices, stock and reorder thresholds.','fields':[
  ('sku','SKU / Reference','text',1),('name','Product name','text',1),('category','Category','text',0),('description','Description','textarea',0),('purchase_price','Purchase price (MAD)','number',0),('selling_price','Selling price (MAD)','number',0),('stock','Current stock','number',0),('min_stock','Minimum stock','number',0),('unit','Unit','text',0)]},
 'sales': {'title':'Sales','singular':'Sale','icon':'bi-graph-up-arrow','desc':'Record sales and monitor revenue.','fields':[
  ('reference','Sale reference','text',1),('customer','Customer','text',1),('date','Sale date','date',1),('subtotal','Subtotal (MAD)','number',1),('tax','Tax (MAD)','number',0),('total','Total (MAD)','number',1),('status','Status','select:Draft,Pending,Paid,Cancelled',0),('payment_method','Payment method','select:Cash,Bank transfer,Card,Cheque,Other',0),('notes','Notes','textarea',0)]},
 'purchases': {'title':'Purchases','singular':'Purchase','icon':'bi-cart-check','desc':'Track supplier purchases and incoming stock.','fields':[
  ('reference','Purchase reference','text',1),('supplier','Supplier','text',1),('date','Purchase date','date',1),('subtotal','Subtotal (MAD)','number',1),('tax','Tax (MAD)','number',0),('total','Total (MAD)','number',1),('status','Status','select:Draft,Pending,Received,Paid,Cancelled',0),('notes','Notes','textarea',0)]},
 'invoices': {'title':'Invoices','singular':'Invoice','icon':'bi-receipt','desc':'Issue and follow customer invoices.','fields':[
  ('number','Invoice number','text',1),('customer','Customer','text',1),('issue_date','Issue date','date',1),('due_date','Due date','date',0),('amount','Amount (MAD)','number',1),('status','Status','select:Draft,Sent,Paid,Overdue,Cancelled',0),('notes','Notes','textarea',0)]},
 'bank_accounts': {'title':'Bank Accounts','singular':'Bank account','icon':'bi-bank','desc':'Manage cash and bank accounts with opening balances.','fields':[
  ('name','Account name','text',1),('bank_name','Bank name','text',0),('account_number','Account number / IBAN','text',0),('currency','Currency','select:MAD,EUR,USD','MAD'),('opening_balance','Opening balance (MAD)','number',1),('notes','Notes','textarea',0)]},
 'bank_transactions': {'title':'Bank Transactions','singular':'Transaction','icon':'bi-arrow-left-right','desc':'Record money in and money out across your accounts.','fields':[
  ('date','Transaction date','date',1),('account','Bank account','text',1),('type','Direction','select:Income,Expense',1),('category','Category','text',0),('description','Description','text',1),('reference','Reference','text',0),('amount','Amount (MAD)','number',1),('method','Method','select:Transfer,Cash,Card,Cheque,Other',0)]},
 'expenses': {'title':'Expenses','singular':'Expense','icon':'bi-wallet2','desc':'Track operating costs and recurring expenses.','fields':[
  ('date','Expense date','date',1),('category','Category','text',1),('description','Description','text',1),('supplier','Supplier','text',0),('amount','Amount (MAD)','number',1),('payment_method','Payment method','select:Cash,Bank transfer,Card,Cheque,Other',0),('status','Status','select:Pending,Paid',0)]},
 'salaries': {'title':'Payroll','singular':'Salary payment','icon':'bi-cash-stack','desc':'Track monthly salaries and payment status.','fields':[
  ('employee','Employee','text',1),('period','Payroll period (YYYY-MM)','text',1),('base_salary','Base salary (MAD)','number',1),('bonus','Bonus (MAD)','number',0),('deductions','Deductions (MAD)','number',0),('net_salary','Net salary (MAD)','number',1),('payment_date','Payment date','date',0),('status','Status','select:Pending,Paid',0)]},
}

SCHEMA = '''
CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, full_name TEXT NOT NULL, created_at TEXT NOT NULL);
'''
for table, spec in MODULES.items():
    cols = ['id INTEGER PRIMARY KEY AUTOINCREMENT']
    for key, label, typ, required in spec['fields']:
        sqltype = 'REAL' if typ == 'number' else 'TEXT'
        cols.append(f'"{key}" {sqltype}')
    cols += ['created_at TEXT NOT NULL', 'updated_at TEXT NOT NULL']
    SCHEMA += f'\nCREATE TABLE IF NOT EXISTS "{table}" ({", ".join(cols)});'


def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute('PRAGMA foreign_keys = ON')
    return g.db

@app.teardown_appcontext
def close_db(exc):
    db = g.pop('db', None)
    if db is not None: db.close()


def init_db():
    db = sqlite3.connect(DB_PATH)
    db.executescript(SCHEMA)
    db.commit()
    count = db.execute('SELECT COUNT(*) FROM users').fetchone()[0]
    if count == 0:
        now = datetime.now().isoformat(timespec='seconds')
        db.execute('INSERT INTO users(username,password_hash,full_name,created_at) VALUES(?,?,?,?)', ('admin', generate_password_hash('Admin@123'), 'CRM Administrator', now))
        seed = {
          'companies': [('Atlas Digital','Technology','ICE-001234','contact@atlas.ma','0522000000','Casablanca, Morocco','Casablanca','https://example.com')],
          'customers': [('Yassine Amrani','Atlas Retail','yassine@example.com','0611223344','ICE-1001','Maarif','Casablanca','Active','Demo customer'),('Nova Market','','hello@nova.example','0600000000','ICE-1002','Rabat','Rabat','Lead','Potential customer')],
          'suppliers': [('Tech Supply Maroc','Sara Benali','sales@supply.example','0522334455','ICE-2001','Sidi Maarouf','Casablanca','30 days','Demo supplier')],
          'employees': [('Sara Benali','Sales Manager','Sales','sara@atlas.example','0612345678','2025-02-01',9500,'Active'),('Omar Idrissi','Accountant','Finance','omar@atlas.example','0622334455','2024-08-15',8500,'Active')],
          'products': [('SKU-001','Laptop Pro 14','Electronics','Business laptop',8200,10500,12,3,'Unit'),('SKU-002','Wireless Mouse','Accessories','Wireless mouse',90,160,42,10,'Unit'),('SKU-003','Office Chair','Furniture','Ergonomic chair',650,990,4,5,'Unit')],
          'sales': [('SAL-2026-001','Yassine Amrani','2026-11-02',10500,2100,12600,'Paid','Bank transfer','Demo sale')],
          'purchases': [('PUR-2026-001','Tech Supply Maroc','2026-10-28',8200,1640,9840,'Received','Demo purchase')],
          'invoices': [('INV-2026-001','Yassine Amrani','2026-11-02','2026-11-30',12600,'Paid','Demo invoice')],
          'bank_accounts': [('Main Business Account','Bank of Morocco','MA000000000000000000000000','MAD',25000,'Demo account')],
          'bank_transactions': [('2026-11-02','Main Business Account','Income','Sales','Payment received','SAL-2026-001',12600,'Transfer'),('2026-11-03','Main Business Account','Expense','Office','Office supplies','EXP-001',850,'Card')],
          'expenses': [('2026-11-03','Office','Office supplies','Local supplier',850,'Card','Paid')],
          'salaries': [('Sara Benali','2026-11',9500,500,0,10000,'2026-11-05','Paid'),('Omar Idrissi','2026-11',8500,0,0,8500,'','Pending')]
        }
        for table, rows in seed.items():
            fields = [f[0] for f in MODULES[table]['fields']]
            placeholders = ','.join('?' for _ in range(len(fields)+2))
            for row in rows:
                db.execute(f'INSERT INTO "{table}" ({",".join(fields)},created_at,updated_at) VALUES ({placeholders})', tuple(row)+(now,now))
        db.commit()
    db.close()


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get('user_id'): return redirect(url_for('login', next=request.path))
        return fn(*args, **kwargs)
    return wrapper

@app.before_request
def csrf_token():
    if 'csrf_token' not in session: session['csrf_token'] = secrets.token_hex(16)

@app.context_processor
def inject_globals():
    return {'modules': MODULES, 'csrf_token': session.get('csrf_token',''), 'current_year': date.today().year}

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        db = get_db(); user = db.execute('SELECT * FROM users WHERE username=?', (request.form.get('username','').strip(),)).fetchone()
        if user and check_password_hash(user['password_hash'], request.form.get('password','')):
            session.clear(); session['user_id'] = user['id']; session['username'] = user['username']; session['full_name'] = user['full_name']; session['csrf_token'] = secrets.token_hex(16)
            flash('Welcome back! You are now signed in.', 'success')
            return redirect(request.args.get('next') or url_for('dashboard'))
        flash('Invalid username or password.', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear(); flash('You have been signed out.', 'info'); return redirect(url_for('login'))

@app.route('/')
@login_required
def dashboard():
    db=get_db()
    def scalar(sql): return db.execute(sql).fetchone()[0] or 0
    stats = {
      'customers': scalar('SELECT COUNT(*) FROM customers'), 'products': scalar('SELECT COUNT(*) FROM products'),
      'sales': scalar("SELECT COALESCE(SUM(total),0) FROM sales WHERE status='Paid'"),
      'expenses': scalar("SELECT COALESCE(SUM(amount),0) FROM expenses WHERE status='Paid'"),
      'invoices_due': scalar("SELECT COUNT(*) FROM invoices WHERE status IN ('Sent','Overdue')"),
      'employees': scalar("SELECT COUNT(*) FROM employees WHERE status='Active'"),
      'low_stock': scalar('SELECT COUNT(*) FROM products WHERE stock <= min_stock'),
      'cash_balance': scalar("SELECT COALESCE(SUM(CASE WHEN type='Income' THEN amount ELSE -amount END),0) FROM bank_transactions")
    }
    recent = db.execute('SELECT * FROM sales ORDER BY id DESC LIMIT 6').fetchall()
    low_stock = db.execute('SELECT * FROM products WHERE stock <= min_stock ORDER BY stock ASC LIMIT 5').fetchall()
    months = db.execute("SELECT substr(date,1,7) month, SUM(total) total FROM sales GROUP BY substr(date,1,7) ORDER BY month DESC LIMIT 6").fetchall()
    return render_template('dashboard.html', stats=stats, recent=recent, low_stock=low_stock, months=list(reversed(months)))

@app.route('/<table>/export')
@login_required
def export_records(table):
    if table not in MODULES: abort(404)
    db=get_db(); spec=MODULES[table]
    fields=[f[0] for f in spec['fields']]
    output=io.StringIO(); writer=csv.writer(output)
    writer.writerow(['ID']+[f[1] for f in spec['fields']]+['Created at','Updated at'])
    rows=db.execute(f'SELECT * FROM "{table}" ORDER BY id DESC').fetchall()
    for row in rows: writer.writerow([row['id']]+[row[k] for k in fields]+[row['created_at'],row['updated_at']])
    filename=f'crm_{table}_{date.today().isoformat()}.csv'
    return Response('\ufeff'+output.getvalue(), mimetype='text/csv', headers={'Content-Disposition':f'attachment; filename={filename}'})

@app.route('/<table>')
@login_required
def list_records(table):
    if table not in MODULES: abort(404)
    spec=MODULES[table]; q=request.args.get('q','').strip(); db=get_db()
    fields=[f[0] for f in spec['fields']]
    if q:
        where=' OR '.join(f'CAST("{f}" AS TEXT) LIKE ?' for f in fields)
        rows=db.execute(f'SELECT * FROM "{table}" WHERE {where} ORDER BY id DESC LIMIT 500', tuple([f'%{q}%']*len(fields))).fetchall()
    else: rows=db.execute(f'SELECT * FROM "{table}" ORDER BY id DESC LIMIT 500').fetchall()
    return render_template('list.html', table=table, spec=spec, fields=spec['fields'], rows=rows, q=q)

@app.route('/<table>/new', methods=['GET','POST'])
@app.route('/<table>/<int:record_id>/edit', methods=['GET','POST'])
@login_required
def edit_record(table, record_id=None):
    if table not in MODULES: abort(404)
    spec=MODULES[table]; db=get_db(); record=None
    if record_id:
        record=db.execute(f'SELECT * FROM "{table}" WHERE id=?',(record_id,)).fetchone()
        if not record: abort(404)
    if request.method=='POST':
        if request.form.get('csrf_token') != session.get('csrf_token'): abort(400)
        values=[]; keys=[]; errors=[]
        for key,label,typ,required in spec['fields']:
            value=request.form.get(key,'').strip()
            if required and not value: errors.append(f'{label} is required.')
            if typ=='number' and value:
                try: value=float(value)
                except ValueError: errors.append(f'{label} must be a number.'); value=0
            keys.append(key); values.append(value or None)
        if errors:
            for err in errors: flash(err,'danger')
            return render_template('form.html', table=table, spec=spec, fields=spec['fields'], record=request.form, is_edit=bool(record_id))
        now=datetime.now().isoformat(timespec='seconds')
        if record_id:
            assignments=','.join(f'"{k}"=?' for k in keys)
            db.execute(f'UPDATE "{table}" SET {assignments}, updated_at=? WHERE id=?', tuple(values)+(now,record_id))
            flash(f'{spec["singular"]} updated successfully.','success')
        else:
            cols=','.join(f'"{k}"' for k in keys); marks=','.join('?' for _ in keys)
            db.execute(f'INSERT INTO "{table}" ({cols},created_at,updated_at) VALUES ({marks},?,?)', tuple(values)+(now,now))
            flash(f'{spec["singular"]} created successfully.','success')
        db.commit(); return redirect(url_for('list_records',table=table))
    return render_template('form.html', table=table, spec=spec, fields=spec['fields'], record=record or {}, is_edit=bool(record_id))

@app.post('/<table>/<int:record_id>/delete')
@login_required
def delete_record(table,record_id):
    if table not in MODULES: abort(404)
    if request.form.get('csrf_token') != session.get('csrf_token'): abort(400)
    db=get_db(); db.execute(f'DELETE FROM "{table}" WHERE id=?',(record_id,)); db.commit()
    flash(f'{MODULES[table]["singular"]} deleted.','info'); return redirect(url_for('list_records',table=table))

@app.route('/settings', methods=['GET','POST'])
@login_required
def settings():
    if request.method=='POST':
        if request.form.get('csrf_token') != session.get('csrf_token'): abort(400)
        old=request.form.get('current_password',''); new=request.form.get('new_password','')
        user=get_db().execute('SELECT * FROM users WHERE id=?',(session['user_id'],)).fetchone()
        if not check_password_hash(user['password_hash'],old): flash('Current password is incorrect.','danger')
        elif len(new)<8: flash('New password must contain at least 8 characters.','danger')
        else:
            get_db().execute('UPDATE users SET password_hash=? WHERE id=?',(generate_password_hash(new),session['user_id'])); get_db().commit(); flash('Password updated successfully.','success')
    return render_template('settings.html')

@app.route('/demo/reset', methods=['POST'])
@login_required
def reset_demo():
    if request.form.get('csrf_token') != session.get('csrf_token'): abort(400)
    db=get_db()
    for table in MODULES: db.execute(f'DELETE FROM "{table}"')
    db.commit(); init_demo_only(); flash('Demo data restored. Your user account was kept.','success'); return redirect(url_for('dashboard'))

def init_demo_only():
    # Reinitialize demo data by running the seed routine against an empty database.
    now=datetime.now().isoformat(timespec='seconds'); db=get_db()
    seed={
      'companies':[('Atlas Digital','Technology','ICE-001234','contact@atlas.ma','0522000000','Casablanca, Morocco','Casablanca','https://example.com')],
      'customers':[('Yassine Amrani','Atlas Retail','yassine@example.com','0611223344','ICE-1001','Maarif','Casablanca','Active','Demo customer'),('Nova Market','','hello@nova.example','0600000000','ICE-1002','Rabat','Rabat','Lead','Potential customer')],
      'suppliers':[('Tech Supply Maroc','Sara Benali','sales@supply.example','0522334455','ICE-2001','Sidi Maarouf','Casablanca','30 days','Demo supplier')],
      'employees':[('Sara Benali','Sales Manager','Sales','sara@atlas.example','0612345678','2025-02-01',9500,'Active'),('Omar Idrissi','Accountant','Finance','omar@atlas.example','0622334455','2024-08-15',8500,'Active')],
      'products':[('SKU-001','Laptop Pro 14','Electronics','Business laptop',8200,10500,12,3,'Unit'),('SKU-002','Wireless Mouse','Accessories','Wireless mouse',90,160,42,10,'Unit'),('SKU-003','Office Chair','Furniture','Ergonomic chair',650,990,4,5,'Unit')],
      'sales':[('SAL-2026-001','Yassine Amrani','2026-11-02',10500,2100,12600,'Paid','Bank transfer','Demo sale')],
      'purchases':[('PUR-2026-001','Tech Supply Maroc','2026-10-28',8200,1640,9840,'Received','Demo purchase')],
      'invoices':[('INV-2026-001','Yassine Amrani','2026-11-02','2026-11-30',12600,'Paid','Demo invoice')],
      'bank_accounts':[('Main Business Account','Bank of Morocco','MA000000000000000000000000','MAD',25000,'Demo account')],
      'bank_transactions':[('2026-11-02','Main Business Account','Income','Sales','Payment received','SAL-2026-001',12600,'Transfer'),('2026-11-03','Main Business Account','Expense','Office','Office supplies','EXP-001',850,'Card')],
      'expenses':[('2026-11-03','Office','Office supplies','Local supplier',850,'Card','Paid')],
      'salaries':[('Sara Benali','2026-11',9500,500,0,10000,'2026-11-05','Paid'),('Omar Idrissi','2026-11',8500,0,0,8500,'','Pending')]
    }
    for table,rows in seed.items():
        fields=[f[0] for f in MODULES[table]['fields']]; marks=','.join('?' for _ in range(len(fields)+2))
        for row in rows: db.execute(f'INSERT INTO "{table}" ({",".join(fields)},created_at,updated_at) VALUES ({marks})',tuple(row)+(now,now))
    db.commit()

@app.route('/health')
def health(): return {'status':'ok','app':'CRM VENDEURE-CLIENT'}

if __name__ == '__main__':
    init_db()
    app.run(host='127.0.0.1', port=int(os.environ.get('PORT',5000)), debug=False)
