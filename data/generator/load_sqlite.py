"""Load agent-visible generated data and corpus into SQLite with FTS5."""
from __future__ import annotations

import csv, json, re, sqlite3
from pathlib import Path

HERE=Path(__file__).resolve().parent; ROOT=HERE.parent; OUT=ROOT/"generated"; DB=OUT/"conduct.sqlite"


def ident(x):
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*",x): raise ValueError(x)
    return '"'+x+'"'


def create_load(conn,name,columns,rows):
    conn.execute(f"DROP TABLE IF EXISTS {ident(name)}")
    conn.execute(f"CREATE TABLE {ident(name)} ({','.join(ident(c)+' TEXT' for c in columns)})")
    if rows: conn.executemany(f"INSERT INTO {ident(name)} VALUES ({','.join('?' for _ in columns)})",[[json.dumps(r.get(c),ensure_ascii=False,sort_keys=True) if isinstance(r.get(c),(dict,list)) else r.get(c) for c in columns] for r in rows])
    if columns and name not in ("transcript_turns","transcript_words","corpus_documents"):
        conn.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS {ident('idx_'+name+'_pk')} ON {ident(name)}({ident(columns[0])})")


def front(path):
    text=path.read_text(); block,body=text.split("---",2)[1:]; m={}
    for line in block.strip().splitlines():
        k,v=line.split(":",1); m[k.strip()]=json.loads(v.strip())
    return m,body.strip()


def main():
    if DB.exists(): DB.unlink()
    conn=sqlite3.connect(DB)
    conn.execute("PRAGMA journal_mode=WAL"); conn.execute("PRAGMA foreign_keys=OFF")
    for p in sorted((OUT/"structured").glob("*.csv")):
        with p.open() as f: r=csv.DictReader(f); create_load(conn,p.stem,r.fieldnames,list(r))
    for folder in ("events","documents"):
        for p in sorted((OUT/folder).glob("*.jsonl")):
            rows=[json.loads(x) for x in p.read_text().splitlines() if x.strip()]
            cols=list(rows[0]) if rows else ["id"]
            name="complaint_narratives" if folder=="documents" and p.stem=="complaints" else p.stem
            create_load(conn,name,cols,rows)
    turns=[]; words=[]
    for p in sorted((OUT/"transcripts").glob("*.json")):
        tr=json.load(p.open())
        for t in tr["turns"]:
            turns.append({"interaction_id":tr["interaction_id"],"turn_id":t["turn_id"],"speaker":t["speaker"],"speaker_confidence":t["speaker_confidence"],"speaker_channel":t["speaker_channel"],"start_s":t["start_s"],"end_s":t["end_s"],"text":t["text"],"source":tr["source"],"language":tr["language"],"asr_model":tr["asr_model"]})
            for n,w in enumerate(t["words"]): words.append({"interaction_id":tr["interaction_id"],"turn_id":t["turn_id"],"word_index":n,**w})
    create_load(conn,"transcript_turns",list(turns[0]),turns); create_load(conn,"transcript_words",list(words[0]),words)
    memories=[json.loads(x) for x in (OUT/"memory_seed"/"agent_memory_notes.jsonl").read_text().splitlines() if x.strip()]
    create_load(conn,"memory_notes",list(memories[0]),memories)
    docs=[]; chunks=[]
    for item in json.load((ROOT/"corpus"/"index.json").open()):
        meta,body=front(ROOT/"corpus"/item["path"]); docs.append({**meta,"path":item["path"],"body":body})
        parts=re.split(r"(?m)(?=^##+ )",body)
        for n,part in enumerate(x.strip() for x in parts if x.strip()):
            head=part.splitlines()[0]; clause=(re.search(r"§([^\s]+)",head) or [None,""])[1]
            chunks.append({"chunk_id":f'{meta["doc_id"]}@{meta["version"]}#{n:03d}',"doc_id":meta["doc_id"],"version":meta["version"],"clause":clause,"effective_from":meta["effective_from"],"effective_to":meta["effective_to"],"status":meta["status"],"text":part})
    create_load(conn,"corpus_documents",list(docs[0]),docs)
    conn.execute("CREATE UNIQUE INDEX idx_corpus_documents_version ON corpus_documents(doc_id, version)")
    create_load(conn,"corpus_chunks",list(chunks[0]),chunks)
    conn.executescript("""
      CREATE VIRTUAL TABLE transcript_fts USING fts5(interaction_id UNINDEXED, turn_id UNINDEXED, speaker UNINDEXED, text);
      INSERT INTO transcript_fts SELECT interaction_id,turn_id,speaker,text FROM transcript_turns;
      CREATE VIRTUAL TABLE corpus_fts USING fts5(chunk_id UNINDEXED, doc_id UNINDEXED, version UNINDEXED, text);
      INSERT INTO corpus_fts SELECT chunk_id,doc_id,version,text FROM corpus_chunks;
      CREATE VIRTUAL TABLE documents_fts USING fts5(document_type UNINDEXED, document_id UNINDEXED, text);
      INSERT INTO documents_fts SELECT 'crm_note',note_id,text FROM crm_notes;
      INSERT INTO documents_fts SELECT 'internal_comm',message_id,text FROM internal_comms;
      INSERT INTO documents_fts SELECT 'complaint',complaint_id,text FROM complaint_narratives;
    """)
    conn.commit(); conn.execute("PRAGMA wal_checkpoint(TRUNCATE)"); conn.close()
    print(f"Built {DB} ({DB.stat().st_size:,} bytes)")


if __name__=="__main__": main()
