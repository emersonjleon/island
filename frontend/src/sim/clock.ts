// Estimate of the server's game time from ping/pong samples. The sample with the
// lowest round trip wins (least queueing), refreshed now and then as clocks drift.

export class ServerClock {
  private offset: number | null = null; // serverMs - localMs
  private bestRtt = Infinity;
  private samples = 0;

  constructor(private readonly local: () => number = () => performance.now()) {}

  /** Record a pong: ``sentAt`` is the local time the ping left, ``serverNow`` the host's game time. */
  sample(sentAt: number, serverNow: number): void {
    const now = this.local();
    const rtt = Math.max(0, now - sentAt);
    this.samples += 1;
    // Let a worse sample in every 20 so a stale best one cannot pin the estimate forever.
    if (rtt <= this.bestRtt || this.samples % 20 === 0 || this.offset === null) {
      this.bestRtt = rtt;
      this.offset = serverNow + rtt / 2 - now;
    }
  }

  /** Fallback before any pong: trust a ``now`` the server stamped on a message. */
  hint(serverNow: number): void {
    if (this.offset === null) this.offset = serverNow - this.local();
  }

  get ready(): boolean {
    return this.offset !== null;
  }

  now(): number {
    return this.local() + (this.offset ?? 0);
  }
}
