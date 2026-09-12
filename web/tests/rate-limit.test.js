import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import { createRateLimiter, clientIpFrom } from '../api/meter/rate-limit.js';

describe('createRateLimiter', () => {
  test('allows requests up to the limit', () => {
    const limiter = createRateLimiter({ limit: 3, windowMs: 60_000 });
    const now = 1_000_000;
    assert.equal(limiter.check('1.2.3.4', now).allowed, true);
    assert.equal(limiter.check('1.2.3.4', now + 1).allowed, true);
    assert.equal(limiter.check('1.2.3.4', now + 2).allowed, true);
  });

  test('blocks the request that would exceed the limit, with a Retry-After estimate', () => {
    const limiter = createRateLimiter({ limit: 2, windowMs: 60_000 });
    const now = 1_000_000;
    limiter.check('9.9.9.9', now);
    limiter.check('9.9.9.9', now + 100);
    const blocked = limiter.check('9.9.9.9', now + 200);
    assert.equal(blocked.allowed, false);
    // Oldest hit (now) expires at now + 60_000; we are at now + 200, so about
    // 59.8s remain — ceil'd to whole seconds.
    assert.equal(blocked.retryAfterSeconds, 60);
  });

  test('does not let one IP consume another IP\'s allowance', () => {
    const limiter = createRateLimiter({ limit: 1, windowMs: 60_000 });
    const now = 1_000_000;
    assert.equal(limiter.check('1.1.1.1', now).allowed, true);
    assert.equal(limiter.check('2.2.2.2', now).allowed, true, 'a different IP must get its own allowance');
    assert.equal(limiter.check('1.1.1.1', now + 1).allowed, false, 'the first IP is still over its own limit');
  });

  test('allows again once the window has fully rolled over', () => {
    const limiter = createRateLimiter({ limit: 1, windowMs: 1000 });
    const now = 1_000_000;
    assert.equal(limiter.check('5.5.5.5', now).allowed, true);
    assert.equal(limiter.check('5.5.5.5', now + 500).allowed, false);
    assert.equal(limiter.check('5.5.5.5', now + 1001).allowed, true, 'the old hit is outside the window now');
  });

  test('rejects a non-positive limit or window at construction, rather than misbehaving silently', () => {
    assert.throws(() => createRateLimiter({ limit: 0, windowMs: 1000 }), TypeError);
    assert.throws(() => createRateLimiter({ limit: 10, windowMs: 0 }), TypeError);
  });

  test('the shared meter limiter matches the spec: 60 per 10 minutes', async () => {
    // Import fresh to read the constant without relying on internal state
    // from other test files (each test file gets its own module registry
    // under node --test).
    const { meterRateLimiter } = await import('../api/meter/rate-limit.js');
    const ip = 'limit-check-only';
    const now = 2_000_000;
    for (let i = 0; i < 60; i++) {
      assert.equal(meterRateLimiter.check(ip, now + i).allowed, true, `request ${i + 1} of 60 should be allowed`);
    }
    assert.equal(meterRateLimiter.check(ip, now + 60).allowed, false, 'the 61st request within 10 minutes must be blocked');
  });
});

describe('clientIpFrom', () => {
  test('prefers the first address in X-Forwarded-For', () => {
    const req = { headers: { 'x-forwarded-for': '203.0.113.5, 70.41.3.18' }, socket: {} };
    assert.equal(clientIpFrom(req), '203.0.113.5');
  });

  test('falls back to the socket address when there is no forwarded header', () => {
    const req = { headers: {}, socket: { remoteAddress: '198.51.100.7' } };
    assert.equal(clientIpFrom(req), '198.51.100.7');
  });

  test('falls back to a constant rather than throwing when nothing identifies the caller', () => {
    const req = { headers: {}, socket: {} };
    assert.equal(clientIpFrom(req), 'unknown');
  });
});
