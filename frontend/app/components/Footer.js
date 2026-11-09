import Link from "next/link";

export default function Footer() {
  return (
    <footer className="site-footer">
      <div className="inner">
        <div>
          <h3>Varsha · वर्षा</h3>
          <p>
            Probabilistic 1–4 week outlooks of monsoon onset, false onset, dry spells and heavy rain at block and
            panchayat level, with crop advisories in Telugu, Hindi and English.
          </p>
          <p>Advisories reach farmers by SMS / WhatsApp only after review by an extension officer.</p>
        </div>
        <div>
          <h3>Quick links</h3>
          <ul>
            <li><Link href="/">Risk map</Link></li>
            <li><Link href="/farmer">Farmer view</Link></li>
            <li><Link href="/officer">Officer console</Link></li>
            <li><Link href="/replay">2023 Kharif replay</Link></li>
            <li><Link href="/skill">Forecast verification</Link></li>
          </ul>
        </div>
        <div>
          <h3>About this prototype</h3>
          <p>Smart India Hackathon 2026 · Problem Statement 26086</p>
          <p>Ministry of Earth Sciences, Government of India</p>
          <p>Pilot region: Mahbubnagar, Nalgonda and Medak districts, Telangana.</p>
        </div>
      </div>
      <div className="bottom">
        <div className="inner">
          <span>Prototype for demonstration — not an official forecast or advisory service.</span>
          <span>Basemap © OpenStreetMap contributors</span>
        </div>
      </div>
    </footer>
  );
}
