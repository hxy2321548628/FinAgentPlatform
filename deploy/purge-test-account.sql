-- P11 步骤三：清掉验收造的测试账号，只留 admin 与 yyyy。
--
-- **外键全是 NO ACTION，没有级联** —— 必须自底向上按拓扑序删，顺序错一处就整个事务回滚。
-- checkpoint 三张表与 run_events、resource_groups、reviews 没有外键（前者是 LangGraph 的，
-- 后三者是多态关联），它们不会拦着删，但留着就是永远查不到主人的孤儿行。
--
-- 整体在一个事务里：中途失败就什么都没发生，不会留下删了一半的库。

BEGIN;

CREATE TEMP TABLE doomed AS
SELECT id FROM users WHERE name NOT IN ('admin', 'yyyy');

CREATE TEMP TABLE doomed_agent AS
SELECT id FROM agents WHERE owner_id IN (SELECT id FROM doomed);

CREATE TEMP TABLE doomed_skill AS
SELECT id FROM skills WHERE owner_id IN (SELECT id FROM doomed);

CREATE TEMP TABLE doomed_group AS
SELECT id FROM groups WHERE owner_id IN (SELECT id FROM doomed);

CREATE TEMP TABLE doomed_thread AS
SELECT id FROM threads WHERE user_id IN (SELECT id FROM doomed);

CREATE TEMP TABLE doomed_run AS
SELECT id FROM runs
WHERE user_id IN (SELECT id FROM doomed)
   OR thread_id IN (SELECT id FROM doomed_thread);

-- ① 多态关联：没有外键拦着，但删了父行它们就成孤儿
DELETE FROM resource_groups
WHERE group_id IN (SELECT id FROM doomed_group)
   OR resource_id IN (SELECT id FROM doomed_agent)
   OR resource_id IN (SELECT id FROM doomed_skill);

DELETE FROM reviews
WHERE submitted_by IN (SELECT id FROM doomed)
   OR reviewed_by IN (SELECT id FROM doomed)
   OR target_id IN (SELECT id FROM doomed_agent)
   OR target_id IN (SELECT id FROM doomed_skill);

-- ② agent 与 skill 各自的版本序列
DELETE FROM agent_versions WHERE agent_id IN (SELECT id FROM doomed_agent);
DELETE FROM agents WHERE id IN (SELECT id FROM doomed_agent);

DELETE FROM skill_versions WHERE skill_id IN (SELECT id FROM doomed_skill);
DELETE FROM skills WHERE id IN (SELECT id FROM doomed_skill);

-- ③ MCP：**这一批全是 P10 验收的夹具**（24 条，都指向 host.docker.internal:8931），
-- 不是平台资产，因此整行删掉。submitted_by 是 NOT NULL，本来也置不成空。
-- 只有 reviewed_by 那一侧才是「审核痕迹」，留着行、把人抹掉
DELETE FROM mcp_servers WHERE submitted_by IN (SELECT id FROM doomed);
UPDATE mcp_servers SET reviewed_by = NULL WHERE reviewed_by IN (SELECT id FROM doomed);

-- ④ 一次分析的全部痕迹：事件 → run → checkpoint → 会话
DELETE FROM run_events WHERE run_id IN (SELECT id FROM doomed_run);
DELETE FROM runs WHERE id IN (SELECT id FROM doomed_run);

-- **checkpoint 的 thread_id 是 32 位无连字符 hex，`uuid::text` 出来的是 36 位带连字符**
-- —— 直接比会一条都匹配不上，而 `DELETE 0` 不报错。2026-08-16 第一次跑就是这么
-- 漏掉 5766 条的，回头按「主人还在不在」反向清才补上。这里一次写对：
DELETE FROM checkpoint_writes WHERE thread_id IN (SELECT replace(id::text, '-', '') FROM doomed_thread);
DELETE FROM checkpoint_blobs  WHERE thread_id IN (SELECT replace(id::text, '-', '') FROM doomed_thread);
DELETE FROM checkpoints       WHERE thread_id IN (SELECT replace(id::text, '-', '') FROM doomed_thread);
DELETE FROM threads WHERE id IN (SELECT id FROM doomed_thread);

-- ⑤ 组：名册与入组申请先走，组本身才删得掉
DELETE FROM user_groups
WHERE user_id IN (SELECT id FROM doomed) OR group_id IN (SELECT id FROM doomed_group);

DELETE FROM group_join_requests
WHERE user_id IN (SELECT id FROM doomed) OR group_id IN (SELECT id FROM doomed_group);

DELETE FROM groups WHERE id IN (SELECT id FROM doomed_group);

-- ⑥ 最后才是账号本身
DELETE FROM users WHERE id IN (SELECT id FROM doomed);

-- 核对：留下来的必须正好是那两个
SELECT name, role FROM users ORDER BY name;

COMMIT;
