import type { Metadata } from "next"
import { Plus_Jakarta_Sans } from "next/font/google"
import "./globals.css"
import { ThemeProvider } from "@/lib/useTheme"
import { ThemeTransitionProvider } from "@/lib/useThemeTransition"

const displayFont = Plus_Jakarta_Sans({
  subsets: ["latin"],
  weight: ["700", "800"],
  variable: "--font-display",
})

export const metadata: Metadata = {
  title: "Campus Virtual Assistant — Poltekkes Kemenkes Yogyakarta",
  description: "Virtual assistant for campus information services",
}

const noFlashThemeScript = `
try {
  var stored = localStorage.getItem('theme');
  if (stored === 'dark') document.documentElement.classList.add('dark');
} catch (e) {}
`

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <head>
        <script dangerouslySetInnerHTML={{ __html: noFlashThemeScript }} />
      </head>
      <body className={displayFont.variable}>
        <ThemeProvider>
          <ThemeTransitionProvider>{children}</ThemeTransitionProvider>
        </ThemeProvider>
      </body>
    </html>
  )
}
