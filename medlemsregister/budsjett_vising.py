"""Interne budsjett og offentleg førehandsvising."""
import json
from flask import abort,redirect,render_template,request,session
from arsdokument import today,DocumentConflict
from database import managed_db
from budsjett import Budgets,CATEGORIES
from rekneskap import ACCOUNTS


def install_budgets(app,get_db,require_admin):
    service=Budgets(get_db)
    app.extensions['budgets']=service

    @app.route('/budsjett',methods=['GET','POST'])
    @require_admin
    def budget_index():
        error=None;status=200
        if request.method=='POST':
            try:
                selected=service.create(request.form.get('year'),session['board_username'])
                return redirect(app.jinja_env.globals['prefix_url']('budget_editor',budget_year=selected))
            except (ValueError,TypeError) as exc: error=str(exc);status=400
        with managed_db(get_db) as db: budgets=db.execute('SELECT * FROM budgets ORDER BY year DESC').fetchall()
        return render_template('budsjett.html',budget=None,budgets=budgets,error=error,default_year=today().year+1),status

    @app.route('/budsjett/<int:budget_year>',methods=['GET','POST'])
    @require_admin
    def budget_editor(budget_year):
        error=None;status=200
        if request.method=='POST':
            try:
                action=request.form.get('action');revision=request.form.get('revision');actor=session['board_username']
                if action=='freeze':
                    service.freeze(budget_year,revision,request.form.get('status'),request.form.get('decision_date',''),actor)
                else: service.update(budget_year,revision,actor,action,request.form)
                return redirect(app.jinja_env.globals['prefix_url']('budget_editor',budget_year=budget_year))
            except (ValueError,TypeError) as exc:
                error=str(exc);status=409 if isinstance(exc,DocumentConflict) else 400
        with managed_db(get_db) as db:
            row=db.execute('SELECT * FROM budgets WHERE year=?',(budget_year,)).fetchone()
            if not row: abort(404)
            versions=db.execute('SELECT * FROM budget_versions WHERE year=? ORDER BY id DESC',(budget_year,)).fetchall()
        return render_template('budsjett.html',budget=row,content=json.loads(row['content']),versions=versions,
                               followup=service.followup(budget_year),accounts=ACCOUNTS,categories=CATEGORIES,
                               values=request.form,error=error),status

    @app.route('/budsjett/versjon/<int:version_id>',methods=['GET','POST'])
    @require_admin
    def budget_version(version_id):
        with managed_db(get_db) as db:
            row=db.execute('SELECT * FROM budget_versions WHERE id=?',(version_id,)).fetchone()
            if not row: abort(404)
        if request.method=='POST':
            if request.form.get('confirmed')!='yes': abort(400,'Stadfest at budsjettet kan publiserast offentleg.')
            service.enqueue(version_id,session['board_username'])
            return redirect(app.jinja_env.globals['prefix_url']('budget_version',version_id=version_id))
        with managed_db(get_db) as db:
            job=db.execute('SELECT * FROM budget_publication_queue WHERE version_id=?',(version_id,)).fetchone()
        return render_template('budsjettversjon.html',report=json.loads(row['payload']),job=job)
