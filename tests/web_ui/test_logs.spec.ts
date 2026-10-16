/**
 * Logs Page Tests
 *
 * Phase 17.2: Pipeline Logging - Logs 페이지 테스트
 */
import { test, expect } from '@playwright/test';

test.describe('Logs Page', () => {
    test.beforeEach(async ({ page }) => {
        await page.goto('/logs');
    });

    // 17.2.1 Logs 페이지 기본 구조
    test('should navigate to logs page', async ({ page }) => {
        // /logs 라우트가 존재해야 한다
        await expect(page).toHaveURL(/.*logs/);
    });

    test('should render logs page title', async ({ page }) => {
        // Logs 페이지 제목이 렌더링되어야 한다
        await expect(page.locator('h1')).toContainText('Logs');
    });

    test('should have logs nav link', async ({ page }) => {
        // 네비게이션에 Logs 링크가 있어야 한다
        const nav = page.locator('nav');
        await expect(nav.locator('text=Logs')).toBeVisible();
    });

    // 17.2.2 로그 목록 표시
    test('should display logs table', async ({ page }) => {
        // 로그 테이블이 표시되어야 한다
        const logsTable = page.locator('[data-testid="logs-table"]');
        await expect(logsTable).toBeVisible();
    });

    test('should show service column', async ({ page }) => {
        // service 컬럼이 표시되어야 한다
        const header = page.locator('[data-testid="logs-table"] th:has-text("Service")');
        await expect(header).toBeVisible();
    });

    test('should show stage column', async ({ page }) => {
        // stage 컬럼이 표시되어야 한다
        const header = page.locator('[data-testid="logs-table"] th:has-text("Stage")');
        await expect(header).toBeVisible();
    });

    test('should show level column', async ({ page }) => {
        // level 컬럼이 표시되어야 한다
        const header = page.locator('[data-testid="logs-table"] th:has-text("Level")');
        await expect(header).toBeVisible();
    });

    test('should show message column', async ({ page }) => {
        // message 컬럼이 표시되어야 한다
        const header = page.locator('[data-testid="logs-table"] th:has-text("Message")');
        await expect(header).toBeVisible();
    });

    test('should show timestamp column', async ({ page }) => {
        // timestamp 컬럼이 표시되어야 한다
        const header = page.locator('[data-testid="logs-table"] th:has-text("Time")');
        await expect(header).toBeVisible();
    });

    // 17.2.3 SSE 실시간 스트리밍
    test('should have SSE connection status indicator', async ({ page }) => {
        // SSE 연결 상태 인디케이터가 있어야 한다
        const indicator = page.locator('[data-testid="sse-status"]');
        await expect(indicator).toBeVisible();
    });

    test('should show auto-refresh toggle', async ({ page }) => {
        // 자동 새로고침 토글이 있어야 한다
        const toggle = page.locator('[data-testid="auto-refresh-toggle"]');
        await expect(toggle).toBeVisible();
    });
});