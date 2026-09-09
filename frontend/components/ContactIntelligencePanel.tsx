"use client";

import {useState} from "react";
import {API_URL} from "@/lib/api";
import type {ContactList} from "@/lib/types";

export default function ContactIntelligencePanel({jobId, initial}: {jobId: number; initial: ContactList}) {
  const [contacts, setContacts] = useState(initial);
  const [preview, setPreview] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<number | null>(null);
  const [discovering, setDiscovering] = useState(false);

  async function discover(force = false) {
    setDiscovering(true);
    setError(null);
    try {
      const response = await fetch(`${API_URL}/jobs/${jobId}/contacts/discover?force=${force}`, {method: "POST"});
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail ?? "Could not search public sources");
      setContacts(body);
      setPreview(null);
    } catch (value) {
      setError(value instanceof Error ? value.message : "Could not search public sources");
    } finally {
      setDiscovering(false);
    }
  }

  async function prepare(contactId: number) {
    setBusy(contactId);
    setError(null);
    try {
      const response = await fetch(`${API_URL}/jobs/${jobId}/contacts/${contactId}/outreach-preview`, {method: "POST"});
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail ?? "Could not prepare outreach");
      setPreview(body.message);
    } catch (value) {
      setError(value instanceof Error ? value.message : "Could not prepare outreach");
    } finally {
      setBusy(null);
    }
  }

  return <section className="panel">
    <p className="panel-label">PEOPLE CLOSE TO THIS ROLE</p>
    <h2>People worth talking to</h2>
    <p>Searches a bounded set of public company, engineering, and research pages only when you ask.</p>
    <div className="card-actions">
      <button type="button" disabled={discovering || busy !== null} onClick={() => discover(contacts.pages_checked > 0)}>
        {discovering ? "Searching public sources…" : contacts.pages_checked > 0 ? "Refresh people" : "Find people close to this role"}
      </button>
    </div>
    {contacts.pages_checked > 0
      ? <small>{contacts.cached ? "Cached results" : "Latest search"}: {contacts.pages_checked} public pages checked, {contacts.candidates_discovered} potential people evaluated.</small>
      : null}
    {!contacts.items.length
      ? <p>{contacts.message ?? "No sufficiently relevant public contacts found yet."}</p>
      : contacts.items.map(contact => <article className="contact-card" key={contact.contact_id}>
          <div><strong>{contact.name}</strong><span>{contact.current_title} · {contact.company}</span></div>
          <p>{contact.relevance_reason}</p>
          <small>Relationship: {contact.relationship_status.replaceAll("_", " ")} ({Math.round(contact.relationship_confidence * 100)}% confidence). Hiring relationship is not assumed.</small>
          <div className="card-actions">
            <a href={contact.source_url} target="_blank" rel="noreferrer">Public source</a>
            <button type="button" disabled={busy !== null || discovering} onClick={() => prepare(contact.contact_id)}>{busy === contact.contact_id ? "Preparing…" : "Prepare outreach"}</button>
          </div>
        </article>)}
    {preview ? <div className="outreach-preview"><b>Grounded outreach preview</b><p>{preview}</p><small>Not sent. Review and edit before using it.</small></div> : null}
    {error ? <p role="alert">{error}</p> : null}
  </section>;
}
