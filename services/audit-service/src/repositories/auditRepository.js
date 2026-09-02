const { getDatabase } = require('../db/database');
const { formatEventResponse } = require('../utils/formatters');

class AuditRepository {

  findAll(limit = 100, offset = 0) {
    const db = getDatabase();
    const rows = db.prepare(
      'SELECT * FROM audit_events ORDER BY created_at DESC LIMIT ? OFFSET ?'
    ).all(limit, offset);
    return rows.map(formatEventResponse);
  }

  findByEventId(eventId) {
    const db = getDatabase();
    const row = db.prepare('SELECT * FROM audit_events WHERE event_id = ?').get(eventId);
    return row ? formatEventResponse(row) : null;
  }

  findByEntityId(entityType, entityId, limit = 50) {
    const db = getDatabase();
    const rows = db.prepare(
      'SELECT * FROM audit_events WHERE entity_type = ? AND entity_id = ? ORDER BY created_at DESC LIMIT ?'
    ).all(entityType, entityId, limit);
    return rows.map(formatEventResponse);
  }

  findByEventType(eventType, limit = 50) {
    const db = getDatabase();
    const rows = db.prepare(
      'SELECT * FROM audit_events WHERE event_type = ? ORDER BY created_at DESC LIMIT ?'
    ).all(eventType, limit);
    return rows.map(formatEventResponse);
  }

  findByDateRange(startDate, endDate, limit = 100) {
    const db = getDatabase();
    const rows = db.prepare(
      'SELECT * FROM audit_events WHERE created_at BETWEEN ? AND ? ORDER BY created_at DESC LIMIT ?'
    ).all(startDate, endDate, limit);
    return rows.map(formatEventResponse);
  }

  create(event) {
    const db = getDatabase();
    
    const stmt = db.prepare(`
      INSERT INTO audit_events 
      (event_id, event_type, entity_type, entity_id, actor, action, details, previous_state, new_state, ip_address, integrity_hash)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `);

    stmt.run(
      event.eventId,
      event.eventType,
      event.entityType,
      event.entityId,
      event.actor,
      event.action,
      event.details ? JSON.stringify(event.details) : null,
      event.previousState ? JSON.stringify(event.previousState) : null,
      event.newState ? JSON.stringify(event.newState) : null,
      event.ipAddress,
      event.integrityHash
    );

    return this.findByEventId(event.eventId);
  }

  countByEntityId(entityType, entityId) {
    const db = getDatabase();
    const result = db.prepare(
      'SELECT COUNT(*) as count FROM audit_events WHERE entity_type = ? AND entity_id = ?'
    ).get(entityType, entityId);
    return result?.count || 0;
  }

  getEventTypes() {
    const db = getDatabase();
    const rows = db.prepare(
      'SELECT DISTINCT event_type FROM audit_events ORDER BY event_type'
    ).all();
    return rows.map(r => r.event_type);
  }
}

module.exports = new AuditRepository();
