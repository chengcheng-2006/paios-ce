# Astron All Products · d32d3ec R1 上传包

这是对桌面压缩包 `Astron-All-Products-d32d3ec-R1.zip` 的审阅整理版，已放入 GitHub 独立交付分支。它把可公开的产品源码与此前生成的中文竞赛演示材料放在一个可读目录中。

## 目录

- [`source/`](source/)：从交付 ZIP 的 `Astron-Delivery/project/` 提取的筛选版产品源码，包含产品 README、源码、测试、示例、演示脚本、协议 schema、治理文件与技术文档。
- [`competition/`](competition/)：七份竞赛文档、四份评审/演示展示稿、脱敏后的历史证据基线、六份演示证据材料和四屏中文静态前端。
- [`dist/ASTRON_COMPETITION_REVIEW_PACKAGE_V1.zip`](dist/ASTRON_COMPETITION_REVIEW_PACKAGE_V1.zip)：按本目录当前中文前端和版本说明重新生成的评审材料 ZIP；旧的评审 ZIP 未直接复用。
- [`manifest/UPLOAD_MANIFEST.json`](manifest/UPLOAD_MANIFEST.json)：来源、计数差异、纳入/排除项及校验记录。
- [`manifest/SOURCE_SHA256SUMS.txt`](manifest/SOURCE_SHA256SUMS.txt)：源码副本各文件的 SHA-256 清单。

## 版本范围

- ZIP 中的产品快照来源：提交 `d32d3ec1bc49a78d0b14aabb6bf0daf79d3f4d88`，源树 `c6953180dcd732c425e77b0acd004321a39837ac`。
- 竞赛实跑基线来源：提交 `11c6114f6ec0504628f912ebde9ba53821badb03`，树 `2d0e6477c7d4e083bbd23e44a7228b7eedb47e24`。这比 ZIP 产品快照更早，不能作为 `d32d3ec` 的实跑或测试证明。
- ZIP 的交付清单称产品目录有 240 个文件；直接核对 ZIP 条目得出 249 个。实际上传的 249 个文件均保留，并在 `UPLOAD_MANIFEST.json` 记录这一计数差异，未静默删改源码来凑清单数字。
- 随包说明记录 546 项测试通过、1 项跳过；本次上传没有重跑测试，因此此处是对原包记录的转述，不是当前分支的新鲜测试收据。

## 未上传的包内内容

GitHub 分支没有收录原 ZIP 内的交接上下文与机器可读交接文件、描述本地工作树的原始装配清单、四个嵌套发行 ZIP（其中包含冻结旧版、重复源码及未公开交接材料），也没有收录内部独立评审文件或本机 `.DS_Store`。它们不属于可公开交付的源码/评审材料。包内原始 `showcase/` 已审阅后复制其中四份用户向材料，并修正过时/过宽的表述；`START_HERE.md` 因其开发者路线指向未公开交接资料而未原样上传。内部基准原始运行目录、SQLite 结果、缓存、holdout/gold 数据也没有纳入这份筛选版；随包说明将其列为有意排除。

这次只创建并推送交付分支，没有创建 GitHub Release 或标签，也没有改动 `main`。
