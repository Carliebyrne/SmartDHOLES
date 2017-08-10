# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.shortcuts import render, redirect
from smart_drillholes.core import *
from .forms import OpenSQliteForm, OpenPostgresForm, NewForm, AddTableForm
import datetime


from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, String, Float
# Views
#from django.views.decorators.csrf import csrf_exempt
#import json
from reflector.og_reflector import Reflector

import os
import re
from django.urls import reverse

def index(request):
    response = render(request,
                      'mainapp/index.html',
                      {'ref': 'index'})
    return response


def open(request):
    if request.method == "GET":
        form = OpenSQliteForm()

    elif request.method == "POST":
        if request.POST['db_type'] == "postgresql":
            form = OpenPostgresForm(request.POST)
        elif request.POST['db_type'] == "sqlite":
            form = OpenSQliteForm(request.POST, request.FILES)
        if form.is_valid():
            if form.cleaned_data.get('db_type') == 'sqlite':
                #content_type: application/octet-stream
                urlfile = request.FILES["sqlite_file"]
                name = form.cleaned_data.get('sqlite_file')

                BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                dbName = BASE_DIR+'/smart4.sqlite'
                if dbName != '':
                    engineURL = 'sqlite:///'+dbName
                #con_string = 'sqlite:///{0}.sqlite'.format(name)
                con_string = engineURL
            elif form.cleaned_data.get('db_type') == 'postgresql':
                host = form.cleaned_data.get('host')
                dbname = form.cleaned_data.get('name')
                user = form.cleaned_data.get('user')
                password = form.cleaned_data.get('password')
                con_string = 'postgresql://{2}:{3}@{0}/{1}'.format(host,dbname,user,password)
                #response = redirect('mainapp:dashboard')

            request.session['engineURL'] = con_string

            reflector = Reflector(con_string)
            reflector.reflectTables()
            cols,tks,data,table_key = update(reflector)

            return render(request,'mainapp/reflector.html', {'tks': tks,'cols':cols,'data':data,'table_key':table_key})
                #return render(request,'mainapp/open.html', {'urlfile':con_string})
            expiry_time = datetime.datetime.now() + datetime.timedelta(minutes=525600)
            response.set_cookie(key='db', value=form.cleaned_data.get('name'), expires=expiry_time)
            response.set_cookie(key='db_type', value=form.cleaned_data.get('db_type'), expires=expiry_time)
            return response
    return render(request,
                     'mainapp/open.html',
                     {'form': form,
                      'ref': 'open'})

def new(request):
    if request.method == "GET":
        form = NewForm()
        return render(request,
                      'mainapp/new.html',
                      {'form': form,
                       'ref': 'new'})
    elif request.method == "POST":
        form = NewForm(request.POST)
        if form.is_valid():
            if form.cleaned_data.get('db_type') == 'sqlite':
                con_string = 'sqlite:///{}.sqlite'.format(form.cleaned_data.get('name'))
            elif form.cleaned_data('db_type') == 'postgresql':

                con_string = 'postgresql://postgres@localhost/{}'.format(form.cleaned_data.get('name'))

            eng, meta = og_connect(con_string)
            og_references(eng, meta, table_name='assay_certificate', key='SampleID', cols={'Au': {'coltypes': Float,
                                                                                           'nullable': True}})
            og_references(eng, meta, table_name='rock_catalog', key='RockID', cols={'Description': {'coltypes': String,
                                                                                                    'nullable': True}})
            og_add_interval(eng, meta, table_name='assay', cols={'SampleID': {'coltypes': String,
                                                                              'nullable': False,
                                                                              'foreignkey': {'column': 'assay_certificate.SampleID',
                                                                                             'ondelete': 'RESTRICT',
                                                                                             'onupdate': 'CASCADE'}}})
            og_add_interval(eng, meta, table_name='litho', cols={'RockID':{'coltypes': String,
                                                                           'nullable': True,
                                                                           'foreignkey': {'column': 'rock_catalog.RockID',
                                                                                          'ondelete': 'RESTRICT',
                                                                                          'onupdate': 'CASCADE'}}})

            execute(eng, meta)

            response = redirect('mainapp:dashboard')
            expiry_time = datetime.datetime.now() + datetime.timedelta(minutes=525600)
            response.set_cookie(key='db', value=form.cleaned_data.get('name'), expires=expiry_time)
            response.set_cookie(key='db_type', value=form.cleaned_data.get('db_type'), expires=expiry_time)
            return response


def dashboard(request):
    response = render(request,
                      'mainapp/dashboard.html',
                      {'ref': 'dashboard'})
    return response

#@csrf_exempt
def reflector(request, table_key = ''):
    engineURL = request.session.get('engineURL')
    reflector = Reflector(engineURL)
    reflector.reflectTables()

    if request.method == 'POST':
        pks = request.POST.getlist('checkbox-delete')
        pp = []
        for i,pk in enumerate(pks):
            pks[i] = pk.split(',')
        table_key = str(request.POST['tablename'])
        Base = declarative_base()
        table = reflector.getOg_table(str(table_key))

        object_table = type(str(table_key), (Base,), defineObject(table))

        if pks:
            session = reflector.make_session()
            for pk in pks:
                query = session.query(object_table).get(pk)
                session.delete(query)
                session.commit()
            session.close()

    cols,tks,data,table_key = update(reflector, table_key)

    return render(request,'mainapp/reflector.html', {'tks': tks,'cols':cols,'data':data,'table_key':table_key})

#Define database Object Table
def defineObject(table):
    columns = table.getColumns()
    tbl_def = {}
    primary_key = False
    nullable = False
    unique = False
    for column in columns:
        if column.primary_key:
            primary_key = True
        else:
            primary_key = False
        if column.nullable:
            nullable = True
        else:
            nullable = False
        if column.unique:
            unique = True
        else:
            unique = False
        tbl_def[column.name] = Column(primary_key = primary_key, nullable = nullable, unique = unique)
    tbl_def['__tablename__'] = table.getName()

    return tbl_def

def update(reflector, table_key = '', session = ''):
    if reflector.is_reflected():
        if session == '':
            session = reflector.make_session()

        #table names for template
        tks = reflector.get_tableKeys()

        data = []
        if table_key != '':
            table = reflector.getOg_table(table_key)
            dat = session.query(reflector.get_metadata().tables[table_key]).all()
        else:
            table_key = tks[0]
            table = reflector.getOg_table(table_key)
            dat = session.query(reflector.get_metadata().tables[tks[0]]).all()

        #columns for template table
        cols = table.getColumnNames()

        #for set primary keys on checkbox delete field
        indxs = table.getPKeysIndex()
        for dt in dat:
            ids = []
            for i in indxs:
                ids.append(str(dt[i]))

            dic = {'pks':','.join(ids),'data':dt}
            data.append(dic)
    session.close()
    del reflector
    return (cols,tks,data,table_key)

def add_table(request):
    if request.method in ['GET', 'POST']:
        if request.COOKIES.get('db_type') == "sqlite":
            con_string = 'sqlite:///{}.sqlite'.format(request.COOKIES.get('db'))
        elif request.COOKIES.get('db_type') == "postgresql":
            con_string = 'postgresql://postgres@localhost/{}'.format(request.COOKIES.get('db'))
        eng, meta = og_connect(con_string)
    if request.method == 'GET':
        form = AddTableForm(meta=meta)
        return render(request,
                      'mainapp/add_table.html',
                      {'ref': 'dashboard', 'form': form})
    elif request.method == 'POST':
        form = AddTableForm(request.POST, meta=meta)
        if form.is_valid():
            if form.cleaned_data.get('table_type') == 'assay_certificate':
                og_references(eng, meta, table_name=form.cleaned_data.get('name'), key='SampleID', cols={'Au': {'coltypes': Float,
                                                                                   'nullable': True}})
            elif form.cleaned_data.get('table_type') == 'rock_catalog':
                og_references(eng, meta, table_name=form.cleaned_data.get('name'), key='RockID', cols={'Description': {'coltypes': String,
                                                                                                        'nullable': True}})
            elif form.cleaned_data.get('table_type') == 'assay':
                table = form.cleaned_data.get('foreignkey')
                for column in meta.tables[table].columns:
                    if column.primary_key:
                        pk = column.key
                og_add_interval(eng, meta, table_name=form.cleaned_data.get('name'), cols={'SampleID': {'coltypes': String,
                                                                                  'nullable': False,
                                                                                  'foreignkey': {'column': '{}.{}'.format(table, pk),
                                                                                                 'ondelete': 'RESTRICT',
                                                                                                 'onupdate': 'CASCADE'}}})
            elif form.cleaned_data.get('table_type') == 'litho':
                for column in meta.tables[table].columns:
                    if column.primary_key:
                        pk = column.key
                og_add_interval(eng, meta, table_name=form.cleaned_data.get('name'), cols={'RockID':{'coltypes': String,
                                                                               'nullable': True,
                                                                               'foreignkey': {'column': '{}.{}'.format(table, pk),
                                                                                              'ondelete': 'RESTRICT',
                                                                                              'onupdate': 'CASCADE'}}})
            execute(eng, meta)
        return redirect('mainapp:dashboard')
