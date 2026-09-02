const express = require('express');
const router = express.Router();
const auditService = require('../services/auditService');

// GET /events - List all events
router.get('/', (req, res, next) => {
  try {
    const limit = parseInt(req.query.limit) || 100;
    const offset = parseInt(req.query.offset) || 0;
    
    const events = auditService.getAllEvents(limit, offset);
    res.json({
      success: true,
      data: events,
      count: events.length,
      pagination: { limit, offset }
    });
  } catch (error) {
    next(error);
  }
});

// GET /events/types - Get available event types
router.get('/types', (req, res, next) => {
  try {
    const types = auditService.getEventTypes();
    res.json({
      success: true,
      data: types
    });
  } catch (error) {
    next(error);
  }
});

// POST /events - Log a new audit event
router.post('/', (req, res, next) => {
  try {
    const eventData = req.body;
    
    if (!eventData || !eventData.eventType) {
      const error = new Error('Event data with eventType is required');
      error.code = 'VALIDATION_ERROR';
      error.status = 400;
      throw error;
    }

    // Add IP address from request
    eventData.ipAddress = req.ip || req.connection?.remoteAddress;

    const event = auditService.logEvent(eventData);
    
    res.status(201).json({
      success: true,
      data: event,
      message: 'Audit event logged'
    });
  } catch (error) {
    next(error);
  }
});

// GET /events/payment/:paymentId - Get events for a payment
router.get('/payment/:paymentId', (req, res, next) => {
  try {
    const events = auditService.getEventsByPaymentId(req.params.paymentId);
    res.json({
      success: true,
      data: events,
      count: events.length
    });
  } catch (error) {
    next(error);
  }
});

// GET /events/payment/:paymentId/trail - Get audit trail for a payment
router.get('/payment/:paymentId/trail', (req, res, next) => {
  try {
    const trail = auditService.getPaymentAuditTrail(req.params.paymentId);
    res.json({
      success: true,
      data: trail
    });
  } catch (error) {
    next(error);
  }
});

// GET /events/account/:accountId - Get events for an account
router.get('/account/:accountId', (req, res, next) => {
  try {
    const events = auditService.getEventsByAccountId(req.params.accountId);
    res.json({
      success: true,
      data: events,
      count: events.length
    });
  } catch (error) {
    next(error);
  }
});

// GET /events/type/:eventType - Get events by type
router.get('/type/:eventType', (req, res, next) => {
  try {
    const events = auditService.getEventsByType(req.params.eventType);
    res.json({
      success: true,
      data: events,
      count: events.length
    });
  } catch (error) {
    next(error);
  }
});

// GET /events/:eventId - Get single event
router.get('/:eventId', (req, res, next) => {
  try {
    const event = auditService.getEventById(req.params.eventId);
    res.json({
      success: true,
      data: event
    });
  } catch (error) {
    next(error);
  }
});

module.exports = router;
