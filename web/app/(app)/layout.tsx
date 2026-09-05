export default function AppLayout({ children }: LayoutProps<"/">) {
  return <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8">{children}</main>;
}
