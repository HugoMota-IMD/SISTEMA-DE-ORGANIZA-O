"""Read-only aggregate integrity check; never print personal financial records."""
import argparse
import hashlib
import json
import sqlite3
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def audit(source):
    path = Path(source)
    path = (path if path.is_absolute() else ROOT/path).resolve()
    if not path.is_relative_to(ROOT) or not path.is_file():
        raise ValueError('Informe um banco existente dentro da raiz exclusiva do projeto.')
    report={'read_only':True,'spaces_checked':0,'installment_entries_checked':0,'incomplete_entries':0,'duplicate_internal_ids':0,'duplicate_installment_numbers':0,'invalid_links':0,'possible_duplicate_entries':0}
    documents=[]
    with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as connection:
        connection.execute('PRAGMA query_only=ON')
        for (raw,) in connection.execute('SELECT document FROM finance_financialstate ORDER BY workspace_id'):
            state=json.loads(raw);documents.append(state);report['spaces_checked']+=1
            for collection in ('accounts','cards','entries','obligations','invoices','payments'):
                counts=Counter(row.get('id') for row in state.get(collection,[]))
                report['duplicate_internal_ids']+=sum(count-1 for count in counts.values() if count>1)
            entries={x['id']:x for x in state.get('entries',[])}
            cards={x['id'] for x in state.get('cards',[])}
            invoices={x['id']:x for x in state.get('invoices',[])}
            signatures=Counter()
            for entry in entries.values():
                if entry.get('kind')!='expense' or entry.get('installments',1)<=1 or entry.get('recurrence_id'):
                    continue
                report['installment_entries_checked']+=1
                parts=[x for x in state.get('obligations',[]) if x.get('entry_id')==entry['id']]
                numbers=Counter(x.get('installment') for x in parts)
                report['duplicate_installment_numbers']+=sum(count-1 for count in numbers.values() if count>1)
                if len(parts)!=entry['installments'] or set(numbers)!=set(range(1,entry['installments']+1)):
                    report['incomplete_entries']+=1
                # An identical signature is only a review candidate, never proof or auto-removal.
                signatures[tuple(str(entry.get(key)) for key in ('description','merchant','amount_cents','installments','purchase_date','due_date','card_id','person_id'))]+=1
            report['possible_duplicate_entries']+=sum(count-1 for count in signatures.values() if count>1)
            for part in state.get('obligations',[]):
                card=part.get('card_id');invoice=part.get('invoice_id')
                if part.get('entry_id') not in entries or (card and card not in cards) or (invoice and (invoice not in invoices or invoices[invoice].get('card_id')!=card)):
                    report['invalid_links']+=1
    report['financial_documents_sha256']=hashlib.sha256(json.dumps(documents,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',default='data/finance.sqlite3')
    parser.add_argument('--output')
    args=parser.parse_args();result=audit(args.source)
    if args.output:
        output=(ROOT/args.output).resolve()
        if not output.is_relative_to(ROOT/'test-results'):
            parser.error('A evidência deve ficar em test-results dentro deste projeto.')
        output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
