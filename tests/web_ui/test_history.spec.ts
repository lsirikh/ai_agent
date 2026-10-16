/**
 * History Page Tests
 *
 * Phase 5.7: Web Dashboard - History 페이지 테스트
 */
import { test, expect } from '@playwright/test';

test.describe('History Page', () => {
    test.beforeEach(async ({ page }) => {
        await page.goto('/history');
    });

    test('should render history page', async ({ page }) => {
        // History 페이지가 렌더링되어야 한다
        await expect(page.locator('h1')).toContainText('History');
    });

    test('should display sessions list', async ({ page }) => {
        // 세션 목록이 표시되어야 한다
        const sessionsList = page.locator('[data-testid="sessions-list"]');
        await expect(sessionsList).toBeVisible();
    });

    test('should display messages list', async ({ page }) => {
        // 메시지 목록이 표시되어야 한다
        const messagesList = page.locator('[data-testid="messages-list"]');
        await expect(messagesList).toBeVisible();
    });

    test('should select session to view messages', async ({ page }) => {
        // 세션을 선택하여 메시지를 볼 수 있어야 한다
        const sessionItem = page.locator('[data-testid="sessions-list"] [data-testid="session-item"]').first();

        if (await sessionItem.isVisible()) {
            await sessionItem.click();

            // 해당 세션의 메시지가 표시되어야 한다
            const messagesList = page.locator('[data-testid="messages-list"]');
            await expect(messagesList).toBeVisible();
        }
    });

    test('should display message with role indicator', async ({ page }) => {
        // 메시지에 역할 표시(user/assistant)가 있어야 한다
        const messageItem = page.locator('[data-testid="messages-list"] [data-testid="message-item"]').first();

        if (await messageItem.isVisible()) {
            const roleIndicator = messageItem.locator('[data-testid="message-role"]');
            await expect(roleIndicator).toBeVisible();
            await expect(roleIndicator).toHaveText(/user|assistant/i);
        }
    });

    test('should display message timestamp', async ({ page }) => {
        // 메시지에 타임스탬프가 표시되어야 한다
        const messageItem = page.locator('[data-testid="messages-list"] [data-testid="message-item"]').first();

        if (await messageItem.isVisible()) {
            const timestamp = messageItem.locator('[data-testid="message-timestamp"]');
            await expect(timestamp).toBeVisible();
        }
    });

    test('should export history as JSON', async ({ page }) => {
        // 기록을 JSON으로 내보낼 수 있어야 한다
        const exportButton = page.locator('button[data-testid="export-json"]');
        await expect(exportButton).toBeVisible();

        // 다운로드 시작 대기
        const [download] = await Promise.all([
            page.waitForEvent('download'),
            exportButton.click()
        ]);

        // 파일명 확인
        expect(download.suggestedFilename()).toMatch(/\.json$/);
    });

    test('should export history as CSV', async ({ page }) => {
        // 기록을 CSV로 내보낼 수 있어야 한다
        const exportButton = page.locator('button[data-testid="export-csv"]');
        await expect(exportButton).toBeVisible();

        // 다운로드 시작 대기
        const [download] = await Promise.all([
            page.waitForEvent('download'),
            exportButton.click()
        ]);

        // 파일명 확인
        expect(download.suggestedFilename()).toMatch(/\.csv$/);
    });

    test('should delete session history', async ({ page }) => {
        // 세션 기록을 삭제할 수 있어야 한다
        const sessionItem = page.locator('[data-testid="sessions-list"] [data-testid="session-item"]').first();

        if (await sessionItem.isVisible()) {
            const deleteButton = sessionItem.locator('[data-testid="delete-session"]');
            await deleteButton.click();

            // 확인 다이얼로그
            await page.click('button:has-text("Confirm")');

            // 성공 메시지 확인
            await expect(page.locator('text=Session deleted')).toBeVisible();
        }
    });

    test('should clear all history', async ({ page }) => {
        // 전체 기록을 삭제할 수 있어야 한다
        const clearAllButton = page.locator('button[data-testid="clear-all-history"]');
        await expect(clearAllButton).toBeVisible();

        await clearAllButton.click();

        // 확인 다이얼로그
        await page.click('button:has-text("Confirm")');

        // 성공 메시지 확인
        await expect(page.locator('text=All history cleared')).toBeVisible();
    });

    test('should paginate messages', async ({ page }) => {
        // 메시지 페이지네이션이 동작해야 한다
        const pagination = page.locator('[data-testid="pagination"]');

        if (await pagination.isVisible()) {
            const nextButton = pagination.locator('button[data-testid="next-page"]');
            const prevButton = pagination.locator('button[data-testid="prev-page"]');

            // 다음 페이지로 이동
            if (await nextButton.isEnabled()) {
                await nextButton.click();
                await expect(page.locator('[data-testid="current-page"]')).toHaveText('2');
            }
        }
    });

    test('should filter messages by date range', async ({ page }) => {
        // 날짜 범위로 메시지를 필터링할 수 있어야 한다
        const dateFilter = page.locator('[data-testid="date-filter"]');

        if (await dateFilter.isVisible()) {
            const startDate = dateFilter.locator('input[name="start-date"]');
            const endDate = dateFilter.locator('input[name="end-date"]');

            await startDate.fill('2024-01-01');
            await endDate.fill('2024-01-31');

            await page.click('button[data-testid="apply-filter"]');

            // 필터가 적용되었는지 확인
            await expect(page.locator('[data-testid="filter-active"]')).toBeVisible();
        }
    });

    test('should search messages', async ({ page }) => {
        // 메시지를 검색할 수 있어야 한다
        const searchInput = page.locator('input[data-testid="message-search"]');

        if (await searchInput.isVisible()) {
            await searchInput.fill('hello');
            await page.keyboard.press('Enter');

            // 검색 결과가 필터링되었는지 확인
            const messages = page.locator('[data-testid="messages-list"] [data-testid="message-item"]');
            const count = await messages.count();

            // 검색어가 포함된 메시지만 표시되어야 함
            for (let i = 0; i < count; i++) {
                const content = await messages.nth(i).locator('[data-testid="message-content"]').textContent();
                expect(content?.toLowerCase()).toContain('hello');
            }
        }
    });

    test('should show empty state when no history', async ({ page }) => {
        // 기록이 없을 때 빈 상태를 표시해야 한다
        const emptyState = page.locator('[data-testid="empty-state"]');
        const sessionsList = page.locator('[data-testid="sessions-list"] [data-testid="session-item"]');

        const count = await sessionsList.count();
        if (count === 0) {
            await expect(emptyState).toBeVisible();
            await expect(emptyState).toContainText('No conversation history');
        }
    });

    test('should display session metadata', async ({ page }) => {
        // 세션 메타데이터가 표시되어야 한다
        const sessionItem = page.locator('[data-testid="sessions-list"] [data-testid="session-item"]').first();

        if (await sessionItem.isVisible()) {
            // 세션 ID, 생성일, 메시지 수 등 확인
            await expect(sessionItem.locator('[data-testid="session-date"]')).toBeVisible();
            await expect(sessionItem.locator('[data-testid="message-count"]')).toBeVisible();
        }
    });
});
