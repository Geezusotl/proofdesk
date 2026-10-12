"""Browser tests. Skipped when Playwright or Chromium is not installed."""
import threading
import unittest

from proofdesk import MockModel, load_folder
from proofdesk.server import App, create_server
from tests.helpers import SAMPLE

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None


@unittest.skipIf(sync_playwright is None, "playwright is not installed")
class GuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = create_server(App(load_folder(SAMPLE), MockModel(), sample=True), "127.0.0.1", 0)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.srv.server_address[1]}/"
        cls.pw = sync_playwright().start()
        try:
            cls.browser = cls.pw.chromium.launch()
        except Exception as exc:  # noqa: BLE001
            cls.pw.stop(); cls.srv.shutdown(); cls.srv.server_close()
            raise unittest.SkipTest(f"no chromium: {exc}")

    @classmethod
    def tearDownClass(cls):
        cls.browser.close(); cls.pw.stop(); cls.srv.shutdown(); cls.srv.server_close()

    def setUp(self):
        self.page = self.browser.new_page(viewport={"width": 1280, "height": 800})
        self.errors = []
        self.page.on("pageerror", lambda e: self.errors.append(str(e)))
        self.page.goto(self.url)
        self.page.wait_for_selector("#doc-list li")

    def tearDown(self):
        self.page.close()
        self.assertEqual(self.errors, [])

    def ask(self, q):
        self.page.fill("#question", q)
        self.page.click("#ask-btn")
        self.page.wait_for_selector("#answer-area .sheet")

    def test_guide_opens_first_time_and_walks_through(self):
        self.assertFalse(self.page.is_hidden("#guide"))
        self.assertIn("Step 1 of 5", self.page.inner_text("#guide-step-label"))
        for _ in range(4):
            self.page.click("#guide-next")
        self.assertIn("Step 5 of 5", self.page.inner_text("#guide-step-label"))
        self.page.click("#guide-next")
        self.assertTrue(self.page.is_hidden("#guide"))

    def test_citation_click_highlights_supporting_sentence(self):
        self.page.click("#guide-close")
        self.ask("What is the company mascot?")
        self.page.click(".cite")
        self.assertIn("purple otter named Brindle", self.page.inner_text("mark.cited"))
        self.assertEqual(self.page.get_attribute(".cite", "aria-pressed"), "true")

    def test_refusal_shown(self):
        self.page.click("#guide-close")
        self.ask("What is the capital of France?")
        self.assertIn("No answer in the documents", self.page.inner_text(".refusal"))
        self.assertEqual(self.page.query_selector_all(".cite"), [])

    def test_html_in_documents_is_not_executed(self):
        self.page.click("#guide-close")
        self.page.click("#add-open")
        self.page.fill("#add-name", "Evil")
        self.page.fill("#add-text", "# Evil\n\nThe secret word is <img src=x onerror=window.__pwn=1> banana.")
        self.page.click("#add-save")
        self.page.wait_for_selector("#page-body p")
        self.ask("What is the secret word?")
        self.assertIsNone(self.page.evaluate("window.__pwn"))
        self.assertIn("<img", self.page.inner_text("#page-body"))

    def test_remove_document(self):
        self.page.click("#guide-close")
        n = len(self.page.query_selector_all("#doc-list li"))
        self.page.once("dialog", lambda d: d.accept())
        self.page.click("#doc-list li .doc-del")
        self.page.wait_for_function("n => document.querySelectorAll('#doc-list li').length === n", arg=n - 1)

    def test_mobile_has_no_horizontal_scroll(self):
        self.page.set_viewport_size({"width": 390, "height": 844})
        self.assertLessEqual(self.page.evaluate("document.documentElement.scrollWidth"), 391)


if __name__ == "__main__":
    unittest.main()
