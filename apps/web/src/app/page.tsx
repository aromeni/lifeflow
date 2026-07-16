import { TryDemoButton } from "@/components/TryDemoButton";

export default function Home() {
  return (
    <main className="mx-auto flex min-h-screen w-full max-w-2xl flex-col justify-center gap-8 px-6 py-16">
      <div className="flex flex-col gap-4">
        <h1 className="text-4xl font-semibold tracking-tight">LifeFlow AI</h1>
        <p className="text-lg">
          Quietly finds what needs attention, explains why it matters, and prepares the next step —
          for your approval.
        </p>
      </div>

      <TryDemoButton />

      <section aria-labelledby="privacy-heading" className="flex flex-col gap-2 text-sm">
        <h2 id="privacy-heading" className="font-medium">
          How your data is handled
        </h2>
        <ul className="list-disc space-y-1 pl-5">
          <li>Reads only a recent window you authorise.</li>
          <li>
            Never sends email or changes your calendar by itself — every action needs your approval.
          </li>
          <li>Disconnect and delete your imported data at any time.</li>
          <li>A full audit trail records everything it observes and does.</li>
        </ul>
        <p className="opacity-70">
          Connecting a real Google account arrives in a later stage; the demo uses entirely
          fictional data.
        </p>
      </section>
    </main>
  );
}
