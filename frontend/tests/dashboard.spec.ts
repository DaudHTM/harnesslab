import { expect, test } from '@playwright/test';

test('create a queued experiment, inspect it, and cancel a run', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Agent reliability, observed.' })).toBeVisible();
  await page.getByRole('button', { name: '+ New demo experiment' }).click();
  await expect(page.getByRole('heading', { name: 'Harness comparison' })).toBeVisible();
  await expect(page.getByText('scripted fixture', { exact: false }).first()).toBeVisible();
  await page.getByRole('button', { name: 'Inspect →' }).first().click();
  await expect(page.getByRole('button', { name: 'Execution trace', exact: false })).toBeVisible();
  await page.getByRole('button', { name: 'Cancel run' }).click();
  await expect(page.getByText('cancelled', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Patch diff' }).click();
  await expect(page.getByText('No patch available yet.')).toBeVisible();
});
