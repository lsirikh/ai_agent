/**
 * Dashboard Page Tests
 *
 * Phase 5.7: Web Dashboard - Dashboard 페이지 테스트
 */
import { test, expect } from '@playwright/test';

test.describe('Dashboard Page', () => {
    test.beforeEach(async ({ page }) => {
        await page.goto('/');
    });

    test('should render dashboard page', async ({ page }) => {
        // Dashboard 페이지가 렌더링되어야 한다
        await expect(page).toHaveTitle(/EdgeVoice/);
        await expect(page.locator('h1')).toContainText('Dashboard');
    });

    test('should display system status card', async ({ page }) => {
        // 시스템 상태 카드가 표시되어야 한다
        const statusCard = page.locator('[data-testid="system-status-card"]');
        await expect(statusCard).toBeVisible();
        await expect(statusCard.locator('text=System Status')).toBeVisible();
    });

    test('should display orchestrator state', async ({ page }) => {
        // Orchestrator 상태가 표시되어야 한다
        const stateIndicator = page.locator('[data-testid="orchestrator-state"]');
        await expect(stateIndicator).toBeVisible();
        // 상태는 IDLE, LISTENING, PROCESSING, SPEAKING 중 하나
        await expect(stateIndicator).toHaveText(/IDLE|LISTENING|PROCESSING|SPEAKING/);
    });

    test('should display service health indicators', async ({ page }) => {
        // 서비스 헬스 인디케이터가 표시되어야 한다
        const healthIndicators = page.locator('[data-testid="service-health"]');
        await expect(healthIndicators).toBeVisible();

        // 각 서비스 상태 확인
        await expect(page.locator('[data-testid="stt-health"]')).toBeVisible();
        await expect(page.locator('[data-testid="llm-health"]')).toBeVisible();
        await expect(page.locator('[data-testid="tts-health"]')).toBeVisible();
    });

    test('should display GPU metrics', async ({ page }) => {
        // GPU 메트릭이 표시되어야 한다
        const gpuMetrics = page.locator('[data-testid="gpu-metrics"]');
        await expect(gpuMetrics).toBeVisible();
        await expect(gpuMetrics.locator('text=GPU')).toBeVisible();
    });

    test('should display CPU and memory usage', async ({ page }) => {
        // CPU 및 메모리 사용량이 표시되어야 한다
        await expect(page.locator('[data-testid="cpu-usage"]')).toBeVisible();
        await expect(page.locator('[data-testid="memory-usage"]')).toBeVisible();
    });

    test('should have navigation menu', async ({ page }) => {
        // 네비게이션 메뉴가 있어야 한다
        const nav = page.locator('nav');
        await expect(nav).toBeVisible();

        // 각 메뉴 항목 확인
        await expect(nav.locator('text=Dashboard')).toBeVisible();
        await expect(nav.locator('text=Settings')).toBeVisible();
        await expect(nav.locator('text=Knowledge')).toBeVisible();
        await expect(nav.locator('text=History')).toBeVisible();
    });

    test('should auto-refresh status data', async ({ page }) => {
        // 상태 데이터가 자동으로 새로고침되어야 한다
        const timestamp = page.locator('[data-testid="last-updated"]');
        await expect(timestamp).toBeVisible();

        // 타임스탬프가 변경되는지 확인 (5초 대기)
        const initialTime = await timestamp.textContent();
        await page.waitForTimeout(5000);
        const updatedTime = await timestamp.textContent();

        // 시간이 변경되었는지 확인 (자동 새로고침)
        expect(updatedTime).not.toBe(initialTime);
    });

    test('should navigate to other pages', async ({ page }) => {
        // 다른 페이지로 네비게이션 가능해야 한다
        await page.click('nav >> text=Settings');
        await expect(page).toHaveURL(/.*settings/);

        await page.click('nav >> text=Knowledge');
        await expect(page).toHaveURL(/.*knowledge/);

        await page.click('nav >> text=History');
        await expect(page).toHaveURL(/.*history/);

        await page.click('nav >> text=Dashboard');
        await expect(page).toHaveURL(/.*\//);
    });
});

/**
 * Phase 17.3.2: Dashboard 서비스 상태 확장 테스트
 */
test.describe('Dashboard Extended Service Status', () => {
    test.beforeEach(async ({ page }) => {
        await page.goto('/');
    });

    test('should display wake_word service status', async ({ page }) => {
        // wake_word 서비스 상태가 표시되어야 한다
        const wakeWordHealth = page.locator('[data-testid="wake-word-health"]');
        await expect(wakeWordHealth).toBeVisible();
        await expect(wakeWordHealth.locator('text=Wake Word')).toBeVisible();
    });

    test('should display audio_gateway service status', async ({ page }) => {
        // audio_gateway 서비스 상태가 표시되어야 한다
        const audioGatewayHealth = page.locator('[data-testid="audio-gateway-health"]');
        await expect(audioGatewayHealth).toBeVisible();
        await expect(audioGatewayHealth.locator('text=Audio Gateway')).toBeVisible();
    });

    test('should display orchestrator service status', async ({ page }) => {
        // orchestrator 서비스 상태가 표시되어야 한다
        const orchestratorHealth = page.locator('[data-testid="orchestrator-health"]');
        await expect(orchestratorHealth).toBeVisible();
        await expect(orchestratorHealth.locator('text=Orchestrator')).toBeVisible();
    });

    test('should show all extended services in grid', async ({ page }) => {
        // 모든 확장 서비스가 그리드에 표시되어야 한다
        const serviceHealth = page.locator('[data-testid="service-health"]');

        // 기존 서비스
        await expect(serviceHealth.locator('[data-testid="stt-health"]')).toBeVisible();
        await expect(serviceHealth.locator('[data-testid="llm-health"]')).toBeVisible();
        await expect(serviceHealth.locator('[data-testid="tts-health"]')).toBeVisible();

        // 확장 서비스
        await expect(serviceHealth.locator('[data-testid="wake-word-health"]')).toBeVisible();
        await expect(serviceHealth.locator('[data-testid="audio-gateway-health"]')).toBeVisible();
        await expect(serviceHealth.locator('[data-testid="orchestrator-health"]')).toBeVisible();
    });
});
