import { describe, it, expect } from 'vitest'
import fc from 'fast-check'

describe('Test infrastructure smoke test', () => {
  it('vitest runs correctly', () => {
    expect(1 + 1).toBe(2)
  })

  it('fast-check works', () => {
    fc.assert(
      fc.property(fc.integer(), (n) => {
        return n + 0 === n
      })
    )
  })
})
