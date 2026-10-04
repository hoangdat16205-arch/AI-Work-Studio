import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from flask import Flask,jsonify
from werkzeug.datastructures import FileStorage
from docx import Document
from pypdf import PdfWriter
from pypdf.generic import NameObject,DictionaryObject,DecodedStreamObject
from studio_workbench import WorkStore,import_document,export_docx,register_workbench
from work_templates import DOMAINS,TEMPLATES,work_request

class WorkbenchTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.base=Path(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def test_task_catalog_and_source_brief(self):
        self.assertEqual(len(DOMAINS),8);self.assertEqual(len(TEMPLATES),32)
        prompt,system,_,_=work_request({'domain':'health','template':'health-medical-summary','brief':'Tóm tắt bài nghiên cứu','source':'Study findings: sample size 10.'})
        self.assertIn('Study findings',prompt);self.assertIn('untrusted reference data',system)
        self.assertIn('Do not infer an individual diagnosis',system)
        with self.assertRaises(ValueError):work_request({'domain':'health','template':'marketing-campaign','brief':'a'})
    def test_document_versioning_and_restart(self):
        store=WorkStore(self.base)
        first=store.save({'title':'Giáo án','domain':'education','body':'Phiên bản đầu','language':'Tiếng Việt'})
        second=store.save({**first,'body':'Phiên bản thứ hai'})
        reopened=WorkStore(self.base)
        self.assertEqual(reopened.get(first['id'])['body'],'Phiên bản thứ hai')
        self.assertEqual(reopened.get(first['id'],1)['body'],'Phiên bản đầu')
        with self.assertRaises(ValueError):store.save({**first,'body':'Bản ghi đè cũ'})
        self.assertEqual(len(store.list('Giáo án','document','education')),1)
        store.archive(first['id']);self.assertEqual(store.list(),[])
        store.archive(first['id'],False);self.assertEqual(len(store.list()),1)
    def test_asset_validation(self):
        directory=self.base/'studio_assets';directory.mkdir();(directory/'image.png').write_bytes(b'png')
        record=WorkStore(self.base).save({'title':'Ảnh','kind':'image','files':[{'id':'image.png','url':'https://external.invalid/'}]})
        self.assertEqual(record['files'][0]['url'],'/assets/image.png')
        with self.assertRaises(ValueError):WorkStore(self.base).save({'title':'Private','kind':'image','files':[{'id':'../.env'}]})
    def test_docx_export_and_import(self):
        buffer=export_docx('Tài liệu tiếng Việt','# Bài học\nNội dung tiếng Việt.\n- Hoạt động nhóm')
        name,content=import_document(FileStorage(stream=buffer,filename='bai_hoc.docx'))
        self.assertEqual(name,'bai_hoc.docx');self.assertIn('Nội dung tiếng Việt.',content)
        self.assertIn('Hoạt động nhóm',content)
    def test_pdf_text_import_and_scanned_pdf(self):
        writer=PdfWriter();page=writer.add_blank_page(width=300,height=200)
        font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
        page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
        stream=DecodedStreamObject();stream.set_data(b'BT /F1 12 Tf 50 100 Td (Hello education) Tj ET')
        page[NameObject('/Contents')]=writer._add_object(stream);buffer=io.BytesIO();writer.write(buffer);buffer.seek(0)
        _,content=import_document(FileStorage(stream=buffer,filename='reference.pdf'))
        self.assertIn('Hello education',content)
        blank=PdfWriter();blank.add_blank_page(width=300,height=200);buffer=io.BytesIO();blank.write(buffer);buffer.seek(0)
        with self.assertRaisesRegex(ValueError,'OCR'):import_document(FileStorage(stream=buffer,filename='scan.pdf'))
    def test_local_project_snapshot(self):
        store=WorkStore(self.base);snapshot={'script':'Lời thoại','workspace':{'title':'Giáo án','body':'Nội dung'},'api_key':'must-not-save'}
        saved=store.save_project({'id':'lesson-01','title':'Bài học','project':snapshot})
        restored=WorkStore(self.base).project('lesson-01')
        self.assertEqual(restored['project']['workspace']['body'],'Nội dung')
        self.assertNotIn('api_key',restored['project'])
        with self.assertRaises(ValueError):store.save_project({'id':'lesson-01','project':snapshot})
        self.assertEqual(store.save_project({'id':'lesson-01','version':saved['version'],'project':snapshot})['version'],2)
    def test_routes_generate_import_export(self):
        calls=[]
        def generate(provider,prompt,system,model):calls.append((provider,prompt,system));return '# Giáo án\nNội dung mẫu.','mock'
        service=SimpleNamespace(text=generate);app=Flask(__name__)
        @app.errorhandler(ValueError)
        def invalid(error):return jsonify(ok=False,error=str(error)),400
        register_workbench(app,self.base,service);client=app.test_client()
        result=client.post('/api/work/generate',json={'provider':'gemini','domain':'education','template':'education-lesson','brief':'Bài học lớp 6'})
        self.assertEqual(result.status_code,200);self.assertEqual(calls[0][0],'gemini');self.assertIn('lesson timeline',calls[0][2])
        self.assertEqual(client.post('/api/work/generate',json={'domain':'unknown','brief':'a'}).status_code,400)
        imported=client.post('/api/work/import',data={'file':(io.BytesIO('Tài liệu gốc'.encode()),'source.txt')}).get_json()
        self.assertEqual(imported['text'],'Tài liệu gốc')
        with client.post('/api/work/export',json={'title':'Bản thảo','body':'<script>alert(1)</script>','format':'html'}) as response:
            self.assertNotIn(b'<script>',response.data);self.assertIn(b'&lt;script&gt;',response.data)
        with client.post('/api/work/export',json={'title':'Bản thảo','body':'Nội dung','format':'docx'}) as response:
            self.assertEqual(response.status_code,200);self.assertTrue(response.data.startswith(b'PK'))
        self.assertEqual(client.post('/api/work/export',json={'body':'','format':'docx'}).status_code,400)

if __name__=='__main__':unittest.main()
