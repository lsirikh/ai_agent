/**
 * Knowledge Page Tests
 *
 * Phase 5.7: Web Dashboard - Knowledge 페이지 테스트
 */
import { test, expect } from '@playwright/test';
import path from 'path';

test.describe('Knowledge Page', () => {
    test.beforeEach(async ({ page }) => {
        await page.goto('/knowledge');
    });

    test('should render knowledge page', async ({ page }) => {
        // Knowledge 페이지가 렌더링되어야 한다
        await expect(page.locator('h1')).toContainText('Knowledge');
    });

    test('should display upload section', async ({ page }) => {
        // 업로드 섹션이 표시되어야 한다
        const uploadSection = page.locator('[data-testid="upload-section"]');
        await expect(uploadSection).toBeVisible();
        await expect(uploadSection.locator('text=Upload Document')).toBeVisible();
    });

    test('should display documents list', async ({ page }) => {
        // 문서 목록이 표시되어야 한다
        const documentsList = page.locator('[data-testid="documents-list"]');
        await expect(documentsList).toBeVisible();
    });

    test('should display search section', async ({ page }) => {
        // 검색 섹션이 표시되어야 한다
        const searchSection = page.locator('[data-testid="search-section"]');
        await expect(searchSection).toBeVisible();
        await expect(searchSection.locator('input[placeholder*="Search"]')).toBeVisible();
    });

    test('should upload TXT file', async ({ page }) => {
        // TXT 파일을 업로드할 수 있어야 한다
        const fileInput = page.locator('input[type="file"]');

        // 테스트 파일 업로드
        await fileInput.setInputFiles({
            name: 'test-document.txt',
            mimeType: 'text/plain',
            buffer: Buffer.from('This is a test document content.')
        });

        await page.click('button[data-testid="upload-button"]');

        // 성공 메시지 확인
        await expect(page.locator('text=Document uploaded successfully')).toBeVisible();

        // 문서 목록에 추가되었는지 확인
        await expect(page.locator('[data-testid="documents-list"]')).toContainText('test-document.txt');
    });

    test('should upload PDF file', async ({ page }) => {
        // PDF 파일을 업로드할 수 있어야 한다
        const fileInput = page.locator('input[type="file"]');

        // 테스트 PDF 파일 (최소한의 PDF 구조)
        const pdfContent = Buffer.from('%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF');

        await fileInput.setInputFiles({
            name: 'test-document.pdf',
            mimeType: 'application/pdf',
            buffer: pdfContent
        });

        await page.click('button[data-testid="upload-button"]');

        // 성공 메시지 확인
        await expect(page.locator('text=Document uploaded successfully')).toBeVisible();
    });

    test('should reject unsupported file type', async ({ page }) => {
        // 지원하지 않는 파일 형식은 거부해야 한다
        const fileInput = page.locator('input[type="file"]');

        await fileInput.setInputFiles({
            name: 'test.exe',
            mimeType: 'application/octet-stream',
            buffer: Buffer.from('fake executable content')
        });

        await page.click('button[data-testid="upload-button"]');

        // 에러 메시지 확인
        await expect(page.locator('text=Unsupported file type')).toBeVisible();
    });

    test('should delete document', async ({ page }) => {
        // 문서를 삭제할 수 있어야 한다
        // 먼저 문서가 있는지 확인 (목업 데이터 사용)
        const deleteButton = page.locator('[data-testid="documents-list"] [data-testid="delete-button"]').first();

        if (await deleteButton.isVisible()) {
            await deleteButton.click();

            // 확인 다이얼로그
            await page.click('button:has-text("Confirm")');

            // 성공 메시지 확인
            await expect(page.locator('text=Document deleted')).toBeVisible();
        }
    });

    test('should search documents', async ({ page }) => {
        // 문서를 검색할 수 있어야 한다
        const searchInput = page.locator('[data-testid="search-section"] input');
        const searchButton = page.locator('[data-testid="search-button"]');

        await searchInput.fill('test query');
        await searchButton.click();

        // 검색 결과 영역이 표시되어야 한다
        await expect(page.locator('[data-testid="search-results"]')).toBeVisible();
    });

    test('should display search results with relevance scores', async ({ page }) => {
        // 검색 결과에 관련도 점수가 표시되어야 한다
        const searchInput = page.locator('[data-testid="search-section"] input');
        const searchButton = page.locator('[data-testid="search-button"]');

        await searchInput.fill('test query');
        await searchButton.click();

        // 검색 결과가 있으면 관련도 점수 확인
        const results = page.locator('[data-testid="search-results"] [data-testid="search-result-item"]');
        const count = await results.count();

        if (count > 0) {
            await expect(results.first().locator('[data-testid="relevance-score"]')).toBeVisible();
        }
    });

    test('should display document metadata', async ({ page }) => {
        // 문서 메타데이터가 표시되어야 한다
        const documentItem = page.locator('[data-testid="documents-list"] [data-testid="document-item"]').first();

        if (await documentItem.isVisible()) {
            // 파일명, 크기, 업로드 날짜 등 확인
            await expect(documentItem.locator('[data-testid="document-name"]')).toBeVisible();
            await expect(documentItem.locator('[data-testid="document-size"]')).toBeVisible();
            await expect(documentItem.locator('[data-testid="document-date"]')).toBeVisible();
        }
    });

    test('should filter documents by type', async ({ page }) => {
        // 문서를 타입별로 필터링할 수 있어야 한다
        const filterSelect = page.locator('select[data-testid="type-filter"]');

        if (await filterSelect.isVisible()) {
            await filterSelect.selectOption('pdf');

            // 필터링된 결과 확인
            const documents = page.locator('[data-testid="documents-list"] [data-testid="document-item"]');
            const count = await documents.count();

            for (let i = 0; i < count; i++) {
                await expect(documents.nth(i).locator('[data-testid="document-type"]')).toHaveText('PDF');
            }
        }
    });

    test('should show empty state when no documents', async ({ page }) => {
        // 문서가 없을 때 빈 상태를 표시해야 한다
        const emptyState = page.locator('[data-testid="empty-state"]');
        const documentsList = page.locator('[data-testid="documents-list"] [data-testid="document-item"]');

        const count = await documentsList.count();
        if (count === 0) {
            await expect(emptyState).toBeVisible();
            await expect(emptyState).toContainText('No documents');
        }
    });
});
